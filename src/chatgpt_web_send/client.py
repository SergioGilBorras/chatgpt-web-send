"""Send prompts through a user-authenticated ChatGPT browser session.

Only the composer and the buttons controlling generation are inspected. No chat
messages or model output are read.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import (
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

BASE_URL = "https://chatgpt.com"
_CONVERSATION_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,256}\Z")
_COMPOSER = (
    '#prompt-textarea[contenteditable="true"], '
    '[data-testid="prompt-textarea"][contenteditable="true"], '
    '[data-testid="composer-input"][contenteditable="true"]'
)
_SEND_BUTTON = (
    'button[data-testid="send-button"], '
    'button[data-testid="composer-send-button"]'
)
_STOP_BUTTON = (
    'button[data-testid="stop-button"], '
    'button[data-testid="stop-response-button"]'
)
# This checks only the contents of the input editor, not any conversation messages.
_COMPOSER_CLEARED_SCRIPT = f"""() => {{
  const input = document.querySelector({_COMPOSER!r});
  return Boolean(input) && !(input.textContent || '').trim();
}}"""


class ChatGPTWebError(Exception):
    """Base error for browser automation failures."""


class AuthenticationRequiredError(ChatGPTWebError):
    """The browser profile needs to be authenticated interactively."""


class SubmissionError(ChatGPTWebError):
    """The editor could not be used or prompt submission was not confirmed."""


class CompletionTimeoutError(ChatGPTWebError):
    """Generation remained active beyond the configured timeout."""


@dataclass(frozen=True)
class SendResult:
    conversation_id: str
    url: str
    submitted: bool
    # True: observed generation stop; None: UI indicator was not available.
    completed: bool | None


def default_profile_dir() -> Path:
    """Persistent, private profile directory; override with an environment variable."""
    override = os.environ.get("CHATGPT_WEB_SEND_PROFILE_DIR")
    return Path(override).expanduser() if override else Path.home() / ".chatgpt-web-send" / "profile"


class ChatGPTWeb:
    """A browser-backed client. Use as a context manager to keep the tab alive.

    Example::

        with ChatGPTWeb() as client:
            result = client.send("conversation-id", "Hello!")
    """

    def __init__(
        self,
        profile_dir: str | Path | None = None,
        *,
        headless: bool = False,
        timeout: float = 30.0,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        self.profile_dir = Path(profile_dir).expanduser() if profile_dir else default_profile_dir()
        self.headless = headless
        self.timeout = timeout
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None

    def __enter__(self) -> ChatGPTWeb:
        if self._context is not None:
            raise ChatGPTWebError("The browser is already open")
        self.profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            self.profile_dir.chmod(0o700)
        self._playwright = sync_playwright().start()
        try:
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=self.headless,
                viewport={"width": 1280, "height": 900},
                accept_downloads=False,
            )
        except Exception:
            self._playwright.stop()
            self._playwright = None
            raise
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Close browser and Playwright, keeping the authenticated profile on disk."""
        try:
            if self._context is not None:
                self._context.close()
        finally:
            self._context = None
            if self._playwright is not None:
                self._playwright.stop()
                self._playwright = None

    def _page(self) -> Page:
        if self._context is None:
            raise ChatGPTWebError("Use 'with ChatGPTWeb() as client:' first")
        return self._context.pages[0] if self._context.pages else self._context.new_page()

    def open_login(self) -> None:
        """Open ChatGPT so the user can sign in themselves; does not read cookies."""
        page = self._page()
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=self.timeout * 1000)

    def send(
        self,
        conversation_id: str,
        prompt: str,
        *,
        wait: bool = True,
        completion_timeout: float = 300.0,
    ) -> SendResult:
        """Submit a prompt; optionally watch only the generation stop control.

        'submitted' means the composer cleared after the send action. This does
        not prove that the server processed the message. Completion is True only
        when a generation activity control was observed and then disappeared;
        otherwise it is None. Never reads existing messages or answer text.
        """
        if not isinstance(conversation_id, str) or not _CONVERSATION_ID_PATTERN.fullmatch(conversation_id):
            raise ValueError("conversation_id must contain only letters, digits, '_' or '-'")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        if completion_timeout <= 0:
            raise ValueError("completion_timeout must be greater than zero")

        url = f"{BASE_URL}/c/{conversation_id}"
        page = self._page()
        page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)

        composer = page.locator(_COMPOSER).first
        try:
            composer.wait_for(state="visible", timeout=self.timeout * 1000)
        except PlaywrightTimeoutError as exc:
            if "/auth/" in urlsplit(page.url).path or "/login" in urlsplit(page.url).path:
                raise AuthenticationRequiredError("Sign in first with: chatgpt-web-send login") from exc
            raise SubmissionError("ChatGPT composer not found. Sign in or check the UI.") from exc

        # A redirect to the home page must never silently send to a new chat.
        parsed = urlsplit(page.url)
        if parsed.hostname != "chatgpt.com" or parsed.path.rstrip("/") != f"/c/{conversation_id}":
            raise SubmissionError("Browser did not remain on the requested conversation URL")

        try:
            composer.fill(prompt)
            send_button = page.locator(_SEND_BUTTON).first
            if send_button.count() and send_button.is_visible() and send_button.is_enabled():
                send_button.click(timeout=self.timeout * 1000)
            else:
                composer.press("Enter", timeout=self.timeout * 1000)
            page.wait_for_function(_COMPOSER_CLEARED_SCRIPT, timeout=self.timeout * 1000)
        except PlaywrightTimeoutError as exc:
            # Do not retry automatically: submission could already have occurred.
            raise SubmissionError("Could not confirm send; do not retry without checking the chat") from exc

        completed = self._wait_for_completion(page, completion_timeout) if wait else None
        return SendResult(conversation_id=conversation_id, url=url, submitted=True, completed=completed)

    @staticmethod
    def _wait_for_completion(page: Page, timeout: float) -> bool | None:
        """Watch only a generation stop button; never inspect answer content."""
        end = time.monotonic() + timeout
        discovery_end = min(end, time.monotonic() + 5.0)
        stop_button = page.locator(_STOP_BUTTON).first
        active_seen = False
        while time.monotonic() < end:
            try:
                is_active = bool(stop_button.count() and stop_button.is_visible())
            except Exception as exc:
                raise ChatGPTWebError("Browser closed while waiting for generation") from exc
            if is_active:
                active_seen = True
            elif active_seen:
                return True
            elif time.monotonic() >= discovery_end:
                return None  # The UI might use different controls.
            page.wait_for_timeout(200)
        if active_seen:
            raise CompletionTimeoutError("The prompt was sent, but generation has not finished")
        return None

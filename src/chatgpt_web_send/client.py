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
# Optional genuine installed browsers, without User-Agent spoofing or
# tampering with automation indicators.
_SUPPORTED_BROWSER_CHANNELS = frozenset(("chrome", "msedge"))
_CONVERSATION_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,256}\Z")
# Restrict fallbacks to the conversation composer: never match editable past messages.
# Some ChatGPT deployments use a textarea, others a ProseMirror/Lexical editor.
_COMPOSER_SELECTORS = (
    '#prompt-textarea[contenteditable="true"]',
    'textarea#prompt-textarea',
    '[data-testid="prompt-textarea"][contenteditable="true"]',
    'textarea[data-testid="prompt-textarea"]',
    '[data-testid="composer-input"][contenteditable="true"]',
    'textarea[data-testid="composer-input"]',
    'textarea[name="prompt-textarea"]',
    'textarea#mobile-composer-prompt',
    'form[data-chatgpt-composer] [contenteditable="true"][role="textbox"]',
    'form [contenteditable="true"][class*="ProseMirror"]',
    'form [contenteditable="true"][data-lexical-editor="true"]',
)
# :visible is Playwright-specific. It avoids selecting hidden fallback textareas.
_COMPOSER = ", ".join(f"{selector}:visible" for selector in _COMPOSER_SELECTORS)
_COMPOSER_DOM = ", ".join(_COMPOSER_SELECTORS)
_SEND_BUTTON = (
    'button[data-testid="send-button"]:visible, '
    'button[data-testid="composer-send-button"]:visible, '
    'button#composer-submit-button:visible, '
    'button[aria-label="Send prompt"]:visible, '
    'button[aria-label="Send message"]:visible, '
    'form[data-chatgpt-composer] button[type="submit"]:visible'
)
_STOP_BUTTON = (
    'button[data-testid="stop-button"], '
    'button[data-testid="stop-response-button"]'
)
# Inspects ONLY the active composer (never the history, answers or page text).
# Textareas store their current prompt in \`value\`, not \`textContent\`.
_COMPOSER_CLEARED_SCRIPT = f"""() => {{
  const editor = Array.from(document.querySelectorAll({_COMPOSER_DOM!r}))
    .find(el => el.getClientRects().length > 0 &&
      getComputedStyle(el).visibility !== 'hidden');
  if (!editor) return false;
  const current = (editor instanceof HTMLTextAreaElement || editor instanceof HTMLInputElement)
    ? editor.value : editor.textContent;
  return !(current || '').trim();
}}"""


class ChatGPTWebError(Exception):
    """Base error for browser automation failures."""


class AuthenticationRequiredError(ChatGPTWebError):
    """The browser profile needs to be authenticated interactively."""


class HumanVerificationRequiredError(ChatGPTWebError):
    """ChatGPT requested interactive verification; automation must stop."""


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


def default_profile_dir(browser_channel: str | None = None) -> Path:
    """Separate persistent browser profiles; retain the legacy Chromium path."""
    override = os.environ.get("CHATGPT_WEB_SEND_PROFILE_DIR")
    if override:
        return Path(override).expanduser()
    base = Path.home() / ".chatgpt-web-send"
    return base / (f"profile-{browser_channel}" if browser_channel else "profile")


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
        timeout: float = 60.0,
        browser_channel: str | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        selected = (
            browser_channel if browser_channel is not None
            else os.environ.get("CHATGPT_WEB_SEND_BROWSER_CHANNEL", "")
        )
        selected = selected.strip().lower()
        if selected and selected not in _SUPPORTED_BROWSER_CHANNELS:
            raise ValueError("browser_channel must be 'chrome', 'msedge', or unset")
        self.browser_channel = selected or None
        self.profile_dir = (
            Path(profile_dir).expanduser()
            if profile_dir else default_profile_dir(self.browser_channel)
        )
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
            options = {
                "user_data_dir": str(self.profile_dir),
                "headless": self.headless,
                "viewport": {"width": 1280, "height": 900},
                "accept_downloads": False,
            }
            if self.browser_channel:
                # Launch the genuine installed browser and keep its real UA.
                # Do not spoof fingerprints or bypass human verification.
                options["channel"] = self.browser_channel
            self._context = self._playwright.chromium.launch_persistent_context(
                **options
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


    @staticmethod
    def _requires_human_verification(page: Page) -> bool:
        """Detect an obvious verification screen without reading chat content.

        This does NOT solve, evade, retry, or interact with a challenge.
        The page title and URL path are all that is inspected.
        """
        try:
            path = urlsplit(str(page.url)).path.casefold()
            if path.startswith(("/cdn-cgi/challenge", "/challenge")):
                return True
            title = page.title()
            return isinstance(title, str) and any(
                indicator in title.casefold()
                for indicator in (
                    "just a moment",
                    "verify you are human",
                    "checking your browser",
                    "human verification",
                    "verifica que eres humano",
                    "verificación humana",
                )
            )
        except Exception:
            # A closed browser or inaccessible document must be diagnosed
            # by the surrounding normal navigation/error handlers.
            return False

    @classmethod
    def _stop_if_verification(cls, page: Page) -> None:
        if cls._requires_human_verification(page):
            raise HumanVerificationRequiredError(
                "ChatGPT is requesting human verification. No prompt was "
                "submitted by this attempt. Inspect the visible browser and "
                "complete any verification yourself; if it repeats, stop "
                "and use the official API for programmatic integrations. "
                "Changing fingerprints or repeating the challenge is not supported."
            )

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
        self._stop_if_verification(page)

        composer = page.locator(_COMPOSER).first
        try:
            composer.wait_for(state="visible", timeout=self.timeout * 1000)
        except PlaywrightTimeoutError as exc:
            # The verification screen may appear after DOMContentLoaded,
            # while we were waiting for the composer.
            self._stop_if_verification(page)
            if "/auth/" in urlsplit(page.url).path or "/login" in urlsplit(page.url).path:
                raise AuthenticationRequiredError("Sign in first with: chatgpt-web-send login") from exc
            raise SubmissionError(
                f"ChatGPT composer not visible after {self.timeout:g}s at {page.url}. "
                "Verify your session, the conversation URL and any login/consent dialog; "
                "try --timeout 90 --keep-open to inspect the browser."
            ) from exc

        # A redirect to the home page must never silently send to a new chat.
        parsed = urlsplit(page.url)
        if parsed.hostname != "chatgpt.com" or parsed.path.rstrip("/") != f"/c/{conversation_id}":
            raise SubmissionError("Browser did not remain on the requested conversation URL")

        try:
            self._stop_if_verification(page)
            composer.fill(prompt)
            self._stop_if_verification(page)
            send_button = page.locator(_SEND_BUTTON).first
            # .click() auto-waits for enablement after filling the editor.
            if send_button.count() and send_button.is_visible():
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

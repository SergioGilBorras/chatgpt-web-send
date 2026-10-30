"""Send prompts through a user-authenticated ChatGPT browser session.

Only the composer and the buttons controlling generation are inspected. No chat
messages or model output are read.
"""

from __future__ import annotations

import os
import re
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
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


def _forbid_default_browser_profile(profile_dir: Path, channel: str | None) -> None:
    """Protect real daily browsing data from unsupported profile automation.

    Playwright/Chrome explicitly do not support the default personal Chrome
    user data directory (Chrome 136+). Never attempt to edit/lock it here.
    """
    if not channel:
        return
    roots: list[Path] = []
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            base = Path(local)
            roots.append(base / ("Google/Chrome/User Data" if channel == "chrome"
                                  else "Microsoft/Edge/User Data"))
    elif sys.platform == "darwin":
        roots.append(Path.home() / ("Library/Application Support/Google/Chrome"
                                   if channel == "chrome"
                                   else "Library/Application Support/Microsoft Edge"))
    elif sys.platform.startswith("linux"):
        roots.append(Path.home() / (".config/google-chrome"
                                   if channel == "chrome" else ".config/microsoft-edge"))
    selected = str(profile_dir.resolve()).casefold()
    for root in roots:
        standard = str(root.resolve()).casefold()
        if selected == standard or selected.startswith(standard + os.sep):
            raise ValueError(
                "Playwright cannot use the normal Chrome/Edge personal profile. "
                "Use its separate persistent profile; run 'chatgpt-web-send open' "
                "to access your existing personal browser session manually."
            )


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
        downloads_dir: str | Path | None = None,
        locale: str | None = None,
        timezone_id: str | None = None,
        verification_grace_seconds: float = 0.0,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if verification_grace_seconds < 0:
            raise ValueError("verification_grace_seconds cannot be negative")
        self.locale = locale
        self.timezone_id = timezone_id
        self.verification_grace_seconds = verification_grace_seconds
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
        _forbid_default_browser_profile(self.profile_dir, self.browser_channel)
        # Downloaded files are exported explicitly; Playwright otherwise
        # deletes accepted downloads on context close.
        self.downloads_dir = (
            Path(downloads_dir).expanduser()
            if downloads_dir is not None else Path.home() / "Downloads"
        )
        self.headless = headless
        self.timeout = timeout
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None

    def __enter__(self) -> ChatGPTWeb:
        if self._context is not None:
            raise ChatGPTWebError("The browser is already open")
        self.profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self.profile_dir.chmod(0o700)
        self._playwright = sync_playwright().start()
        try:
            options = {
                "user_data_dir": str(self.profile_dir),
                "headless": self.headless,
                # Playwright otherwise adds --no-sandbox by default. Keep the
                # normal Chromium/Edge sandbox enabled for all browser channels.
                "chromium_sandbox": True,
                # Use native window sizing rather than a fixed emulated viewport.
                "no_viewport": True,
                "accept_downloads": True,
            }
            if self.locale:
                options["locale"] = self.locale
            if self.timezone_id:
                options["timezone_id"] = self.timezone_id
            if self.browser_channel:
                # Launch the genuine installed browser and keep its real UA.
                # Do not spoof fingerprints or bypass human verification.
                options["channel"] = self.browser_channel
            self._context = self._playwright.chromium.launch_persistent_context(
                **options
            )
            # In persistent contexts the browser maintains its own history,
            # bookmarks, downloads UI and sign-in inside this *separate* profile.
            # Playwright removes temporary downloaded files on close; save a
            # user-visible copy into the chosen Downloads directory.
            self._context.on("page", self._watch_downloads)
            for page in self._context.pages:
                self._watch_downloads(page)
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


    def _watch_downloads(self, page: Page) -> None:
        page.on("download", self._save_download)

    def _save_download(self, download: object) -> None:
        """Preserve accepted downloads; never inspect their contents.

        The filename is untrusted, so use an unpredictable prefix and strip
        directory components. Do not overwrite preexisting user files.
        """
        raw = str(download.suggested_filename).replace("\\", "/")
        basename = raw.rsplit("/", 1)[-1]
        basename = re.sub(r"[^A-Za-z0-9._ -]", "_", basename)[:120].strip(" .")
        safe_name = basename or "download"
        destination = self.downloads_dir / f"chatgpt-{uuid.uuid4().hex}-{safe_name}"
        try:
            download.save_as(str(destination))
        except Exception:
            # Do not print remote URLs, file names or other private data.
            raise ChatGPTWebError("Could not save a browser download")

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

    def _wait_for_manual_verification(self, page: Page) -> None:
        """Allow a visible challenge to clear; never interact with the challenge.

        The optional grace period does not retry a send or attempt to solve a
        CAPTCHA. A user can complete verification in the visible browser.
        """
        if not self._requires_human_verification(page):
            return
        deadline = time.monotonic() + self.verification_grace_seconds
        while time.monotonic() < deadline:
            page.wait_for_timeout(min(400, max(1, (deadline - time.monotonic()) * 1000)))
            if not self._requires_human_verification(page):
                return
        self._stop_if_verification(page)

    def _page(self) -> Page:
        if self._context is None:
            raise ChatGPTWebError("Use 'with ChatGPTWeb() as client:' first")
        return self._context.pages[0] if self._context.pages else self._context.new_page()

    def browser_info(self) -> dict[str, str]:
        """Inspect browser metadata only; never access chat messages or cookies."""
        page = self._page()
        user_agent = page.evaluate("() => navigator.userAgent")
        return {
            "channel": self.browser_channel or "playwright-chromium",
            "user_agent": str(user_agent),
            "profile_dir": str(self.profile_dir),
            "downloads_dir": str(self.downloads_dir),
        }

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
        self._wait_for_manual_verification(page)

        composer = page.locator(_COMPOSER).first
        try:
            composer.wait_for(state="visible", timeout=self.timeout * 1000)
        except PlaywrightTimeoutError as exc:
            # The verification screen may appear after DOMContentLoaded,
            # while we were waiting for the composer.
            self._wait_for_manual_verification(page)
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
            self._wait_for_manual_verification(page)
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

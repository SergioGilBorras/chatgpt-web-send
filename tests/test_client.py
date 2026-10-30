from unittest.mock import MagicMock

import pytest

from chatgpt_web_send import ChatGPTWeb, ChatGPTWebError, SubmissionError
from chatgpt_web_send.client import _COMPOSER, _COMPOSER_CLEARED_SCRIPT


def browser_client():
    client = ChatGPTWeb(timeout=1)
    page = MagicMock()
    page.url = "https://chatgpt.com/c/abc-123"
    composer = MagicMock()
    send_button = MagicMock()
    send_button.count.return_value = 1
    send_button.is_visible.return_value = True
    send_button.is_enabled.return_value = True
    page.locator.side_effect = [MagicMock(first=composer), MagicMock(first=send_button)]
    client._context = MagicMock()
    client._context.pages = [page]
    return client, page, composer, send_button


def test_send_only_fills_composer_and_clicks_send():
    client, page, composer, button = browser_client()
    result = client.send("abc-123", "Hola\nMundo", wait=False)
    assert result.submitted is True
    assert result.completed is None
    composer.fill.assert_called_once_with("Hola\nMundo")
    button.click.assert_called_once()
    page.wait_for_function.assert_called_once()
    assert page.locator.call_count == 2  # editor and send button; never messages


def test_falls_back_to_enter_without_button():
    client, _, composer, button = browser_client()
    button.count.return_value = 0
    client.send("abc-123", "Hola", wait=False)
    composer.press.assert_called_once()


@pytest.mark.parametrize("value", ["", "../foo", "x?z=1", "https://evil.example", "one/two"])
def test_rejects_invalid_id(value):
    client = ChatGPTWeb()
    with pytest.raises(ValueError):
        client.send(value, "Hola", wait=False)


def test_rejects_empty_prompt():
    client = ChatGPTWeb()
    with pytest.raises(ValueError):
        client.send("abc", " \n ", wait=False)


def test_refuses_redirect_to_wrong_conversation():
    client, page, _, _ = browser_client()
    page.url = "https://chatgpt.com/"
    with pytest.raises(SubmissionError, match="requested conversation"):
        client.send("abc-123", "Hola", wait=False)


def test_context_manager_required():
    with pytest.raises(ChatGPTWebError, match="with ChatGPTWeb"):
        ChatGPTWeb().open_login()


def test_supports_textareas_without_matching_hidden_inputs():
    assert "textarea#prompt-textarea:visible" in _COMPOSER
    assert 'textarea[name="prompt-textarea"]:visible' in _COMPOSER
    assert "textarea#mobile-composer-prompt:visible" in _COMPOSER
    assert "editor.value" in _COMPOSER_CLEARED_SCRIPT
    assert "getClientRects" in _COMPOSER_CLEARED_SCRIPT


def test_composer_is_waited_for_and_timeout_is_actionable():
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    client, page, composer, _ = browser_client()
    composer.wait_for.side_effect = PlaywrightTimeoutError("not found")
    with pytest.raises(SubmissionError, match="--timeout 90 --keep-open"):
        client.send("abc-123", "Hola", wait=False)
    composer.wait_for.assert_called_once_with(state="visible", timeout=1000)


def test_uses_send_button_even_when_initially_disabled():
    client, page, composer, button = browser_client()
    button.is_enabled.return_value = False
    client.send("abc-123", "Hola", wait=False)
    button.click.assert_called_once()
    composer.press.assert_not_called()


def test_verification_screen_aborts_without_typing_or_sending():
    from chatgpt_web_send.client import HumanVerificationRequiredError

    client, page, composer, button = browser_client()
    page.title.return_value = "Just a moment..."
    with pytest.raises(HumanVerificationRequiredError, match="human verification"):
        client.send("abc-123", "PRIVATE TEST PROMPT", wait=False)
    composer.fill.assert_not_called()
    button.click.assert_not_called()
    composer.press.assert_not_called()


def test_verification_after_editor_wait_is_reported():
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from chatgpt_web_send.client import HumanVerificationRequiredError

    client, page, composer, button = browser_client()
    composer.wait_for.side_effect = PlaywrightTimeoutError("composer absent")
    page.title.side_effect = ["ChatGPT", "Verify you are human"]
    with pytest.raises(HumanVerificationRequiredError):
        client.send("abc-123", "PRIVATE TEST PROMPT", wait=False)
    composer.fill.assert_not_called()
    button.click.assert_not_called()


def test_challenge_path_detected_without_reading_page_content():
    from chatgpt_web_send.client import HumanVerificationRequiredError

    client, page, composer, button = browser_client()
    page.url = "https://chatgpt.com/cdn-cgi/challenge-platform/some-id"
    with pytest.raises(HumanVerificationRequiredError):
        client.send("abc-123", "PRIVATE TEST PROMPT", wait=False)
    page.title.assert_not_called()
    composer.fill.assert_not_called()
    button.click.assert_not_called()


def test_normal_chat_page_is_not_flagged_as_challenge():
    client, page, _, button = browser_client()
    page.title.return_value = "ChatGPT"
    result = client.send("abc-123", "Safe dummy text", wait=False)
    assert result.submitted is True
    button.click.assert_called_once()


def test_non_string_page_title_is_not_mistaken_for_challenge():
    client, page, _, _ = browser_client()
    page.title.return_value = None
    assert client._requires_human_verification(page) is False


def test_browser_channel_uses_real_installed_edge_without_spoofing(tmp_path):
    from unittest.mock import patch

    client = ChatGPTWeb(profile_dir=tmp_path / "edge", browser_channel="msedge")
    driver = MagicMock()
    with patch("chatgpt_web_send.client.sync_playwright") as playwright:
        playwright.return_value.start.return_value = driver
        with client:
            pass
    options = driver.chromium.launch_persistent_context.call_args.kwargs
    assert options["channel"] == "msedge"
    assert options["headless"] is False
    assert options["chromium_sandbox"] is True
    assert "user_agent" not in options
    assert "args" not in options


def test_bundled_chromium_remains_default(tmp_path, monkeypatch):
    from unittest.mock import patch

    monkeypatch.delenv("CHATGPT_WEB_SEND_BROWSER_CHANNEL", raising=False)
    client = ChatGPTWeb(profile_dir=tmp_path / "old-profile")
    driver = MagicMock()
    with patch("chatgpt_web_send.client.sync_playwright") as playwright:
        playwright.return_value.start.return_value = driver
        with client:
            pass
    options = driver.chromium.launch_persistent_context.call_args.kwargs
    assert "channel" not in options
    assert options["chromium_sandbox"] is True
    assert "user_agent" not in options


def test_browser_profiles_are_isolated_by_channel(tmp_path, monkeypatch):
    monkeypatch.setattr("chatgpt_web_send.client.Path.home", lambda: tmp_path)
    monkeypatch.delenv("CHATGPT_WEB_SEND_PROFILE_DIR", raising=False)
    monkeypatch.delenv("CHATGPT_WEB_SEND_BROWSER_CHANNEL", raising=False)
    root = tmp_path / ".chatgpt-web-send"
    assert ChatGPTWeb().profile_dir == root / "profile"
    assert ChatGPTWeb(browser_channel="chrome").profile_dir == root / "profile-chrome"
    assert ChatGPTWeb(browser_channel="msedge").profile_dir == root / "profile-msedge"


def test_explicit_profile_overrides_environment_default(tmp_path, monkeypatch):
    monkeypatch.setenv("CHATGPT_WEB_SEND_BROWSER_CHANNEL", "msedge")
    monkeypatch.setenv("CHATGPT_WEB_SEND_PROFILE_DIR", str(tmp_path / "shared"))
    client = ChatGPTWeb()
    assert client.browser_channel == "msedge"
    assert client.profile_dir == tmp_path / "shared"
    selected = ChatGPTWeb(browser_channel="chrome", profile_dir=tmp_path / "dedicated")
    assert selected.browser_channel == "chrome"
    assert selected.profile_dir == tmp_path / "dedicated"


@pytest.mark.parametrize("channel", ["firefox", "safari", "chrome-canary", "../edge"])
def test_unsupported_browser_channel_fails_closed(channel):
    with pytest.raises(ValueError, match="browser_channel"):
        ChatGPTWeb(browser_channel=channel)


def test_native_browser_window_downloads_and_persistent_history(tmp_path):
    from unittest.mock import patch

    client = ChatGPTWeb(profile_dir=tmp_path / "profile",
                        downloads_dir=tmp_path / "my-downloads",
                        browser_channel="msedge")
    playwright = MagicMock()
    with patch("chatgpt_web_send.client.sync_playwright") as mocked:
        mocked.return_value.start.return_value = playwright
        with client:
            pass
    options = playwright.chromium.launch_persistent_context.call_args.kwargs
    assert options["channel"] == "msedge"
    assert options["accept_downloads"] is True
    assert options["no_viewport"] is True
    assert options["chromium_sandbox"] is True
    assert "viewport" not in options
    assert options["user_data_dir"] == str(tmp_path / "profile")
    assert (tmp_path / "my-downloads").is_dir()
    assert playwright.chromium.launch_persistent_context.return_value.on.call_args.args[0] == "page"


def test_browser_download_is_saved_with_unique_filename(tmp_path):
    client = ChatGPTWeb(profile_dir=tmp_path / "profile",
                        downloads_dir=tmp_path / "downloads")
    client.downloads_dir.mkdir()
    download = MagicMock()
    download.suggested_filename = r"..\\..\\private.pdf"
    client._save_download(download)
    saved = download.save_as.call_args.args[0]
    destination = __import__("pathlib").Path(saved)
    assert destination.parent == tmp_path / "downloads"
    assert destination.name.startswith("chatgpt-")
    assert destination.name.endswith("private.pdf")
    assert ".." not in destination.name


def test_doctor_reads_only_browser_metadata_not_conversation(tmp_path):
    client, page, _, _ = browser_client()
    client.downloads_dir = tmp_path
    page.evaluate.return_value = "Mozilla/5.0 Edg/139.0"
    info = client.browser_info()
    assert info["user_agent"] == "Mozilla/5.0 Edg/139.0"
    assert info["channel"] == "playwright-chromium"
    page.evaluate.assert_called_once_with("() => navigator.userAgent")
    page.goto.assert_not_called()


def test_rejects_windows_default_edge_profile(monkeypatch, tmp_path):
    monkeypatch.setattr("chatgpt_web_send.client.sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    normal = tmp_path / "Local" / "Microsoft" / "Edge" / "User Data"
    with pytest.raises(ValueError, match="normal Chrome/Edge personal profile"):
        ChatGPTWeb(profile_dir=normal, browser_channel="msedge")
    with pytest.raises(ValueError, match="normal Chrome/Edge personal profile"):
        ChatGPTWeb(profile_dir=normal / "Default", browser_channel="msedge")


def test_optional_locale_timezone_are_forwarded_without_spoofing(tmp_path):
    from unittest.mock import patch

    client = ChatGPTWeb(profile_dir=tmp_path / "profile", locale="es-ES",
                        timezone_id="Europe/Madrid")
    driver = MagicMock()
    with patch("chatgpt_web_send.client.sync_playwright") as mocked:
        mocked.return_value.start.return_value = driver
        with client:
            pass
    options = driver.chromium.launch_persistent_context.call_args.kwargs
    assert options["locale"] == "es-ES"
    assert options["timezone_id"] == "Europe/Madrid"
    assert options["chromium_sandbox"] is True
    assert "user_agent" not in options
    assert "ignore_default_args" not in options


def test_manual_challenge_waits_for_user_then_continues():
    client, page, composer, button = browser_client()
    client.verification_grace_seconds = 10.0
    page.title.side_effect = ["Verify you are human", "ChatGPT", "ChatGPT", "ChatGPT"]
    result = client.send("abc-123", "Prueba", wait=False)
    assert result.submitted is True
    page.wait_for_timeout.assert_called()
    composer.fill.assert_called_once_with("Prueba")
    button.click.assert_called_once()


def test_negative_verification_grace_is_rejected():
    with pytest.raises(ValueError, match="verification_grace_seconds"):
        ChatGPTWeb(verification_grace_seconds=-1)

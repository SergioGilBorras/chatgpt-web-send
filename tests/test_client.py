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

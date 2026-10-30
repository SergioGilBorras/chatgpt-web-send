from unittest.mock import MagicMock, patch

from chatgpt_web_send.cli import main
from chatgpt_web_send.client import SendResult, SubmissionError


def test_cli_sends_prompt():
    client = MagicMock()
    client.send.return_value = SendResult("abc", "https://chatgpt.com/c/abc", True, None)
    context = MagicMock()
    context.__enter__.return_value = client
    with patch("chatgpt_web_send.cli.ChatGPTWeb", return_value=context):
        assert main(["send", "--conversation-id", "abc", "--prompt", "Hola", "--no-wait"]) == 0
    client.send.assert_called_once_with(
        conversation_id="abc", prompt="Hola", wait=False, completion_timeout=300.0
    )


def test_keep_open_waits_on_failure(capsys):
    client = MagicMock()
    client.send.side_effect = SubmissionError("Editor not visible")
    context = MagicMock()
    context.__enter__.return_value = client
    with patch("chatgpt_web_send.cli.ChatGPTWeb", return_value=context), patch("builtins.input") as ask:
        assert main(["send", "--conversation-id", "abc", "--prompt", "Hola", "--keep-open"]) == 1
    ask.assert_called_once()
    assert "Browser left open for inspection" in capsys.readouterr().out


def test_browser_channel_passes_from_cli_to_client():
    client = MagicMock()
    client.send.return_value = SendResult("abc", "https://chatgpt.com/c/abc", True, None)
    ctx = MagicMock()
    ctx.__enter__.return_value = client
    with patch("chatgpt_web_send.cli.ChatGPTWeb", return_value=ctx) as ctor:
        assert main(["send", "--browser-channel", "msedge",
                     "--conversation-id", "abc", "--prompt", "Dummy", "--no-wait"]) == 0
    assert ctor.call_args.kwargs["browser_channel"] == "msedge"


def test_cli_rejects_unlisted_browser_channel():
    import pytest

    with pytest.raises(SystemExit) as err:
        main(["login", "--browser-channel", "unknown"])
    assert err.value.code == 2


def test_open_uses_existing_system_browser_without_launching_playwright(capsys):
    with patch("chatgpt_web_send.cli.webbrowser.open_new_tab", return_value=True) as open_browser, \
         patch("chatgpt_web_send.cli.ChatGPTWeb") as browser:
        result = main(["open", "--conversation-id", "abc-123"])
    assert result == 0
    open_browser.assert_called_once_with("https://chatgpt.com/c/abc-123")
    browser.assert_not_called()
    assert "regular browser" in capsys.readouterr().out


def test_open_rejects_invalid_conversation_id():
    with patch("chatgpt_web_send.cli.webbrowser.open_new_tab") as open_browser:
        assert main(["open", "--conversation-id", "../x"]) == 2
    open_browser.assert_not_called()


def test_doctor_reports_real_browser_and_downloads_without_navigating(capsys):
    client = MagicMock()
    client.browser_info.return_value = {
        "channel": "msedge", "user_agent": "Mozilla/5.0 Edg/139.0",
        "profile_dir": "profile-edge", "downloads_dir": "Downloads",
    }
    ctx = MagicMock()
    ctx.__enter__.return_value = client
    with patch("chatgpt_web_send.cli.ChatGPTWeb", return_value=ctx) as constructor:
        assert main(["doctor", "--browser-channel", "msedge"]) == 0
    assert constructor.call_args.kwargs["browser_channel"] == "msedge"
    assert "Actual browser channel: msedge" in capsys.readouterr().out
    client.browser_info.assert_called_once()


def test_doctor_keep_open_waits_for_user():
    client = MagicMock()
    client.browser_info.return_value = {
        "channel": "chrome", "user_agent": "Chrome", "profile_dir": "p", "downloads_dir": "d"
    }
    ctx = MagicMock()
    ctx.__enter__.return_value = client
    with patch("chatgpt_web_send.cli.ChatGPTWeb", return_value=ctx), \
         patch("builtins.input") as ask:
        assert main(["doctor", "--browser-channel", "chrome", "--keep-open"]) == 0
    ask.assert_called_once()

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

from unittest.mock import MagicMock, patch

from chatgpt_web_send.cli import main
from chatgpt_web_send.client import SendResult


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

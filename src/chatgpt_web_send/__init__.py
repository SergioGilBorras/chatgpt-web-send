"""Browser-based, send-only ChatGPT automation."""

from .client import (
    AuthenticationRequiredError,
    ChatGPTWeb,
    ChatGPTWebError,
    CompletionTimeoutError,
    SendResult,
    SubmissionError,
    default_profile_dir,
)

__version__ = "0.1.0"
__all__ = [
    "AuthenticationRequiredError",
    "ChatGPTWeb",
    "ChatGPTWebError",
    "CompletionTimeoutError",
    "SendResult",
    "SubmissionError",
    "default_profile_dir",
]

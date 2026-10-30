"""Browser-based, send-only ChatGPT automation."""

from .client import (
    AuthenticationRequiredError,
    ChatGPTWeb,
    ChatGPTWebError,
    HumanVerificationRequiredError,
    CompletionTimeoutError,
    SendResult,
    SubmissionError,
    default_profile_dir,
)

__version__ = "0.1.3"
__all__ = [
    "AuthenticationRequiredError",
    "ChatGPTWeb",
    "ChatGPTWebError",
    "HumanVerificationRequiredError",
    "CompletionTimeoutError",
    "SendResult",
    "SubmissionError",
    "default_profile_dir",
]

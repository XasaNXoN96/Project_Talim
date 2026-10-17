import logging
import re

# Password-reset links carry a one-time token in the URL path; query strings may carry anything. Never log them.
_RESET_PATH = re.compile(r"(/accounts/reset/[^/\s\"']+/)[^/\s\"']+(/?)")
_ASSIGNMENT = re.compile(r"(?i)\b(password|passwd|token|secret|code)=[^\s&\"']+")
_QUERY = re.compile(r"(\?)[^\s\"']*")


def redact(text: str) -> str:
    text = _RESET_PATH.sub(r"\1[redacted]\2", text)
    text = _ASSIGNMENT.sub(r"\1=[redacted]", text)
    return text


class RedactSecretsFilter(logging.Filter):
    """Removes reset tokens and credential-like key=value pairs from log lines before they are emitted."""

    def filter(self, record):
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 — malformed log call: leave it alone
            return True
        cleaned = redact(message)
        if cleaned != message:
            record.msg, record.args = cleaned, ()
        return True

"""Redact sensitive values from text content."""

import re

_REDACTED = "***REDACTED***"

# key=value or key: value — redact the value part.
_SENSITIVE_KEY_NAMES = [
    "passwd",
    "password",
    "secret_key",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "credentials",
    "auth_token",
    "client_secret",
    "session_token",
    "CAVECLIENT_MICRONS_API_KEY",
]
_KEY_VALUE_RE = re.compile(
    r"(?i)((?:" + "|".join(_SENSITIVE_KEY_NAMES) + r")[\s]*[=:]\s*)([^\s\"',;}{]+)"
)

# AWS access key IDs (AKIA + 16 alphanumeric)
_AWS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")

# Bearer tokens
_BEARER_RE = re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9\-._~+/]+=*")

# Long base64 strings (64+ chars, likely tokens/keys)
_BASE64_RE = re.compile(r"\b[A-Za-z0-9+/]{64,}={0,2}\b")


def redact_sensitive(text: str) -> str:
    """Replace sensitive values in text with a redaction placeholder."""
    text = _KEY_VALUE_RE.sub(rf"\1{_REDACTED}", text)
    text = _AWS_KEY_RE.sub(_REDACTED, text)
    text = _BEARER_RE.sub(rf"\1{_REDACTED}", text)
    text = _BASE64_RE.sub(_REDACTED, text)
    return text

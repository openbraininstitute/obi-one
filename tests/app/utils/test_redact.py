"""Tests for sensitive data redaction."""

import pytest

from app.utils.redact import redact_sensitive

_R = "***REDACTED***"


@pytest.mark.parametrize(
    ("input_text", "expected"),
    [
        # aws access key IDs
        ("key is AKIAIOSFODNN7EXAMPLE", f"key is {_R}"),
        # key=value secrets
        ("SECRET_KEY=myobisecret2026", f"SECRET_KEY={_R}"),
        ("password=toogoodtobetrue", f"password={_R}"),
        ("api_key: sk-abc123def456789ghi", f"api_key: {_R}"),
        ("token=eyJhbGciOiJIUzI1NiJ9.payload.sig", f"token={_R}"),
        ("CAVECLIENT_MICRONS_API_KEY=micronskey123", f"CAVECLIENT_MICRONS_API_KEY={_R}"),
        # Bearer tokens
        (
            "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9",
            f"Authorization: Bearer {_R}",
        ),
        # safe text should pass through unchanged
        ("INFO: Processing 42 neurons in region CA1", "INFO: Processing 42 neurons in region CA1"),
        ("status: running", "status: running"),
        (
            '{"message_type": "log", "value": "done"}',
            '{"message_type": "log", "value": "done"}',
        ),
    ],
)
def test_redact_sensitive(input_text, expected):
    assert redact_sensitive(input_text) == expected

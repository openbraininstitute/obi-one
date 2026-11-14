"""Keep the signature of presigned storage URLs out of logs.

The URL reaches the logs from several loggers: httpx2 logs every request URL at INFO, and
entitysdk quotes the redirected URL in its errors. The API installs ``RedactPresignedCredentials``
on the root handler (``app.application``), so one filter covers them all. Only the
credential parameters of an S3 presigned URL are redacted: the other query parameters,
such as entitycore search filters, stay readable for debugging.
"""

import logging
import re
from collections.abc import Mapping

# The S3 SigV4 query parameters that grant access; the rest of a presigned URL does not.
PRESIGNED_PARAMETER_PATTERN = re.compile(
    r"((?:^|[?&])X-Amz-(?:Signature|Credential|Security-Token)=)[^&\s'\"#]*",
    re.IGNORECASE | re.MULTILINE,
)
REDACTED_VALUE = "<redacted>"


def redact_presigned_credentials(text: str) -> str:
    """Replace the value of every S3 presigned-URL credential parameter in ``text``."""
    return PRESIGNED_PARAMETER_PATTERN.sub(rf"\1{REDACTED_VALUE}", text)


def _redact_argument(value: object) -> object:
    """A log argument with its credentials redacted; non-string arguments are kept."""
    return redact_presigned_credentials(value) if isinstance(value, str) else value


class RedactPresignedCredentials(logging.Filter):
    """Log filter: redact presigned-URL credentials in a record's message and traceback."""

    def filter(self, record: logging.LogRecord) -> bool:  # ruff: ignore[no-self-use]
        """Redact the record in place and always keep it."""
        try:
            message = record.getMessage()
        # Handler.handle runs filters outside Handler.emit's try, so a malformed call
        # ("%s" without its argument) would raise into the caller. Redact the parts and
        # let emit report it as "--- Logging error ---", as it does without this filter.
        except Exception:  # ruff: ignore[blind-except]
            record.msg = _redact_argument(record.msg)
            if isinstance(record.args, Mapping):
                record.args = {key: _redact_argument(v) for key, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(map(_redact_argument, record.args))
        else:
            record.msg = redact_presigned_credentials(message)
            record.args = None
        if record.exc_info and not record.exc_text:
            # Formatted once here; Formatter prints exc_text instead of exc_info.
            record.exc_text = redact_presigned_credentials(
                logging.Formatter().formatException(record.exc_info)
            )
        return True

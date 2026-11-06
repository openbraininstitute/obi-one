"""Keep URL query strings, where presigned URLs carry their signature, out of logs.

The URL reaches the logs from several loggers: httpx2 logs every request URL at INFO, and
entitysdk quotes the redirected URL in its errors. The API installs ``RedactUrlQueries``
on the root handler (``app.application``), so one filter covers them all.
"""

import logging
import re

URL_QUERY_PATTERN = re.compile(r"(https?://[^\s?#'\"]+)\?[^\s'\"]*")
REDACTED_QUERY = "?<redacted>"


def redact_url_queries(text: str) -> str:
    """Replace the query string of every http(s) URL in ``text``; host and path stay."""
    return URL_QUERY_PATTERN.sub(rf"\1{REDACTED_QUERY}", text)


class RedactUrlQueries(logging.Filter):
    """Log filter: redact URL query strings in a record's message and traceback."""

    def filter(self, record: logging.LogRecord) -> bool:  # ruff: ignore[no-self-use]
        """Redact the record in place and always keep it."""
        record.msg = redact_url_queries(record.getMessage())
        record.args = None
        if record.exc_info and not record.exc_text:
            # Formatted once here; Formatter prints exc_text instead of exc_info.
            record.exc_text = redact_url_queries(
                logging.Formatter().formatException(record.exc_info)
            )
        return True

"""Keep the query strings of URLs, where presigned URLs carry their secrets, out of logs.

entitysdk follows the redirect from entitycore to a presigned storage URL and chains the
HTTP client's error, whose message holds that full URL. A log call with ``exc_info``
prints the chain, so the signature would reach the logs. ``RedactUrlQueries`` removes
every query string from a record before a handler formats it; the scheme, host and path
stay, so the log still says which file failed.
"""

import logging
import re

URL_QUERY_PATTERN = re.compile(r"(https?://[^\s?#'\"]+)\?[^\s'\"]*")
REDACTED_QUERY = "?<redacted>"


def redact_url_queries(text: str) -> str:
    """Replace the query string of every http(s) URL in ``text``."""
    return URL_QUERY_PATTERN.sub(rf"\1{REDACTED_QUERY}", text)


class RedactUrlQueries(logging.Filter):
    """Logger filter: redact URL query strings in a record's message and traceback.

    The traceback is formatted here once and stored in ``exc_text``, which the standard
    ``logging.Formatter`` prints instead of formatting ``exc_info`` again.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # ruff: ignore[no-self-use]
        """Redact the record in place and always keep it."""
        record.msg = redact_url_queries(record.getMessage())
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = redact_url_queries(
                logging.Formatter().formatException(record.exc_info)
            )
        return True

"""Sentry integration."""

import sentry_sdk

from app.config import settings


def init_sentry() -> None:
    """Initialize the Sentry SDK.

    A no-op when ``SENTRY_DSN`` is unset: ``sentry_sdk.init`` with ``dsn=None`` disables
    reporting, so local development and tests send nothing. Sentry's FastAPI/Starlette and
    standard-logging integrations are auto-enabled and capture unhandled exceptions.
    """
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.DEPLOYMENT_ENV,
        release=settings.APP_VERSION,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        profile_session_sample_rate=settings.SENTRY_PROFILE_SESSION_SAMPLE_RATE,
        profile_lifecycle="trace",
    )

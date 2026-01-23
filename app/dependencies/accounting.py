from obp_accounting_sdk._async.factory import AsyncAccountingSessionFactory  # noqa: PLC2701

from app.config import settings


def get_accounting_factory() -> AsyncAccountingSessionFactory:
    """Get an accounting session factory instance."""
    factory = AsyncAccountingSessionFactory(
        base_url=settings.ACCOUNTING_BASE_URL,
        disabled=settings.ACCOUNTING_DISABLED,
    )
    return factory

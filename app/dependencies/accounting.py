from obp_accounting_sdk._sync.factory import AccountingSessionFactory

from app.config import settings


def get_accounting_factory() -> AccountingSessionFactory:
    """Get an accounting session factory instance."""
    factory = AccountingSessionFactory(
        base_url=settings.ACCOUNTING_BASE_URL,
        disabled=settings.ACCOUNTING_DISABLED,
    )
    return factory

from typing import Annotated

from fastapi import Depends
from obp_accounting_sdk import AccountingSessionFactory

from app.config import settings


def get_accounting_factory() -> AccountingSessionFactory:
    return AccountingSessionFactory(
        base_url=settings.ACCOUNTING_BASE_URL,
        disabled=settings.ACCOUNTING_DISABLED,
    )


AccountingSessionFactoryDep = Annotated[AccountingSessionFactory, Depends(get_accounting_factory)]

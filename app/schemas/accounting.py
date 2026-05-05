from obp_accounting_sdk.constants import ServiceSubtype

from app.schemas.base import Schema


class AccountingParameters(Schema):
    service_subtype: ServiceSubtype
    count: int

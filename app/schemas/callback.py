from app.schemas.base import Schema
from app.types import CallBackAction, CallBackEvent


class HttpRequestCallBackConfig(Schema):
    url: str
    method: str
    params: dict | None = None
    headers: dict | None = None
    payload: dict | None = None


class CallBack(Schema):
    action_type: CallBackAction
    event_type: CallBackEvent
    config: HttpRequestCallBackConfig

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.errors import ApiErrorCode


class Schema(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", from_attributes=True)


class ErrorResponse(BaseModel, use_enum_values=True):
    """ErrorResponse."""

    error_code: ApiErrorCode
    message: str
    details: Any = None


class OptionalProjectContext(BaseModel):
    virtual_lab_id: UUID | None = None
    project_id: UUID | None = None

from uuid import UUID

from pydantic import ConfigDict

from app.schemas.base import Schema


class JobRead(Schema):
    """Job data returned from the launch-system.

    Uses flexible types so changes in the launch-system schema don't break things
    """

    model_config = ConfigDict(frozen=True, extra="allow", from_attributes=True)

    id: UUID
    project_id: UUID
    user_id: UUID
    status: str
    error_reason: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    logs: dict | None = None
    inputs: list[str] | None = None
    meta: dict | None = None
    created_at: str | None = None
    updated_at: str | None = None

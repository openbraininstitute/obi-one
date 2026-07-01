"""Schemas for the contributor registration endpoints."""

from typing import Annotated, Literal
from uuid import UUID

from entitysdk.types import AgentType
from pydantic import BaseModel, Field


class PersonPreview(BaseModel):
    """Preview of a person resolved from an ORCID."""

    identifier: str
    identifier_type: Literal["orcid"] = "orcid"
    agent_type: Literal[AgentType.person] = AgentType.person
    name: str
    given_name: str | None = None
    family_name: str | None = None
    orcid: str
    already_registered: bool = False
    existing_id: UUID | None = None


class OrganizationPreview(BaseModel):
    """Preview of an organization resolved from a ROR ID."""

    identifier: str
    identifier_type: Literal["ror"] = "ror"
    agent_type: Literal[AgentType.organization] = AgentType.organization
    name: str
    alternative_name: str | None = None
    ror_id: str
    already_registered: bool = False
    existing_id: UUID | None = None


ContributorPreview = Annotated[
    PersonPreview | OrganizationPreview,
    Field(discriminator="agent_type"),
]

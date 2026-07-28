"""Schemas for the contributor registration endpoints."""

from typing import Annotated, Literal
from uuid import UUID

from entitysdk.types import AgentType
from pydantic import BaseModel, Field

from app.types import IdentifierType


class PersonPreview(BaseModel):
    """Preview of a person resolved from an ORCID."""

    identifier: str
    identifier_type: Literal[IdentifierType.orcid] = IdentifierType.orcid
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
    identifier_type: Literal[IdentifierType.ror] = IdentifierType.ror
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


class OrcidMetadata(BaseModel):
    """Metadata for a person fetched from the ORCID API."""

    orcid: str
    given_name: str | None = None
    family_name: str | None = None
    pref_label: str


class RorMetadata(BaseModel):
    """Metadata for an organization fetched from the ROR API."""

    ror_id: str
    name: str
    alternative_names: list[str] = Field(default_factory=list)
    types: list[str] = Field(default_factory=list)
    country: str | None = None

import logging
import uuid
from datetime import datetime, timedelta
from enum import StrEnum, auto
from typing import Annotated, ClassVar

import entitysdk
from pydantic import BaseModel, Field, PrivateAttr

from obi_one.core.block import Block
from obi_one.core.form import Form
from obi_one.core.single import SingleCoordinateMixin

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Authentication and authorization errors."""

    SETUP_BLOCK_GROUP = "Setup"
    ASSET_BLOCK_GROUP = "Morphology files"
    CONTRIBUTOR_BLOCK_GROUP = "Experimenter"
    STRAIN_BLOCK_GROUP = "Animal strain"
    LICENSE_GROUP = "License"
    LOCATION_GROUP = "Location"
    PROTOCOL_GROUP = "Protocol"


class Sex(StrEnum):
    male = auto()
    female = auto()
    unknown = auto()


class AgePeriod(StrEnum):
    prenatal = auto()
    postnatal = auto()
    unknown = auto()


class StatusEnum(StrEnum):
    active = "active"
    inactive = "inactive"
    pending = "pending"


class Contribution(BaseModel):
    name: str = Field(default="", description="Contribution name")
    status: StatusEnum = Field(default=StatusEnum.pending, description="Status")


class Author(BaseModel):
    given_name: str | None = None
    family_name: str | None = None


class Reference(BaseModel):
    type: str = Field(..., description="Reference type (e.g. DOI, PubMed)")
    identifier: str = Field(..., description="Unique reference identifier")

    class Config:
        json_schema_extra: ClassVar[dict[str, str]] = {"title": "Reference"}


class Publication(Block):
    name: str = Field(default="", description="Publication name")
    description: str = Field(default="", description="Publication description")
    DOI: str | None = Field(default="")
    publication_title: str | None = Field(default="")
    authors: Author | None = Field(default=None)
    publication_year: int | None = Field(default=None)
    abstract: str | None = Field(default="")

    class Config:
        json_schema_extra: ClassVar[dict[str, str]] = {"title": "Publication"}


class MTypeClassification(Block):
    mtype_class_id: uuid.UUID | None = Field(
        default=None, description="UUID for MType classification"
    )


class Assets(Block):
    swc_file: str | None = Field(default=None, description="SWC file for the morphology.")
    asc_file: str | None = Field(default=None, description="ASC file for the morphology.")
    h5_file: str | None = Field(default=None, description="H5 file for the morphology.")


class ReconstructionMorphology(Block):
    name: str = Field(description="Name of the morphology")  # Add default
    description: str = Field(description="Description")  # Add default
    species_id: uuid.UUID | None = Field(default=None)  # Make nullable with default
    strain_id: uuid.UUID | None = Field(default=None)
    brain_region_id: uuid.UUID | None = Field(default=None)  # Make nullable
    legacy_id: list[str] | None = Field(default=None)


class Subject(Block):
    name: str = Field(default="", description="Subject name")
    description: str = Field(default="", description="Subject description")
    sex: Annotated[Sex, Field(title="Sex", description="Sex of the subject")] = Sex.unknown

    weight: float | None = Field(
        default=None,
        title="Weight",
        description="Weight in grams",
        gt=0.0,
        json_schema_extra={"default": None},
    )
    age_value: timedelta | None = Field(
        default=None,
        title="Age value",
        description="Age value interval.",
        gt=timedelta(0),
    )
    age_min: timedelta | None = Field(
        default=None,
        title="Minimum age range",
        description="Minimum age range",
        gt=timedelta(0),
    )
    age_max: timedelta | None = Field(
        default=None,
        title="Maximum age range",
        description="Maximum age range",
        gt=timedelta(0),
    )
    age_period: AgePeriod | None = AgePeriod.unknown

    model_config: ClassVar[dict[str, str]] = {"extra": "forbid"}


class License(Block):
    license_id: uuid.UUID | None = Field(default=None)


class ScientificArtifact(Block):
    experiment_date: datetime | None = Field(default=None)
    contact_email: str | None = Field(default=None)
    atlas_id: uuid.UUID | None = Field(default=None)


class ContributeMorphologyForm(Form):
    """Contribute Morphology Form."""

    single_coord_class_name: ClassVar[str] = "ContributeMorphology"
    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    class Config:
        json_schema_extra: ClassVar[dict[str, list[BlockGroup]]] = {
            "block_block_group_order": [
                BlockGroup.SETUP_BLOCK_GROUP,
                BlockGroup.ASSET_BLOCK_GROUP,
                BlockGroup.CONTRIBUTOR_BLOCK_GROUP,
                BlockGroup.STRAIN_BLOCK_GROUP,
                BlockGroup.LOCATION_GROUP,
                BlockGroup.PROTOCOL_GROUP,
                BlockGroup.LICENSE_GROUP,
            ]
        }

    assets: Assets = Field(
        default_factory=Assets,
        title="Assets",
        description="Morphology files.",
        group=BlockGroup.SETUP_BLOCK_GROUP,
        group_order=0,
    )

    contribution: Contribution = Field(
        default_factory=Contribution,
        title="Contribution",
        description="Contributor.",
        group=BlockGroup.SETUP_BLOCK_GROUP,
        group_order=1,
    )

    morphology: ReconstructionMorphology = Field(
        default_factory=ReconstructionMorphology,
        title="Morphology",
        description="Information about contributors.",
        group=BlockGroup.CONTRIBUTOR_BLOCK_GROUP,
        group_order=0,
    )

    subject: Subject = Field(
        default_factory=Subject,
        title="Subject",
        description="Information about the subject.",
        group=BlockGroup.CONTRIBUTOR_BLOCK_GROUP,
        group_order=0,
    )

    publication: Publication = Field(
        default_factory=Publication,
        title="Publication Details",
        description="Publication details.",
        group=BlockGroup.CONTRIBUTOR_BLOCK_GROUP,
        group_order=0,
    )

    license: License = Field(
        default_factory=License,
        title="License",
        description="The license used.",
        group=BlockGroup.CONTRIBUTOR_BLOCK_GROUP,
        group_order=0,
    )

    scientificartifact: ScientificArtifact = Field(
        default_factory=ScientificArtifact,
        title="Scientific Artifact",
        description="Information about the artifact.",
        group=BlockGroup.CONTRIBUTOR_BLOCK_GROUP,
        group_order=0,
    )

    mtype: MTypeClassification = Field(
        default_factory=MTypeClassification,
        title="Mtype Classification",
        description="The mtype.",
        group=BlockGroup.CONTRIBUTOR_BLOCK_GROUP,
        group_order=0,
    )


class ContributeMorphology(ContributeMorphologyForm, SingleCoordinateMixin):
    """Placeholder here to maintain compatibility."""

    CONFIG_FILE_NAME: ClassVar[str] = ""
    NODE_SETS_FILE_NAME: ClassVar[str] = ""

    _sonata_config: dict = PrivateAttr(default={})

    def generate(self, db_client: entitysdk.client.Client = None) -> None:
        pass

    def save(
        self,
        campaign: entitysdk.models.SimulationCampaign,
        db_client: entitysdk.client.Client,
    ) -> None:
        pass

import logging
import uuid
from datetime import datetime, timedelta
from enum import StrEnum, auto
from typing import Annotated, ClassVar

import entitysdk
from pydantic import BaseModel, Field

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Authentication and authorization errors."""

    SETUP_BLOCK_GROUP = "Basic information"
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


class Contribution(BaseModel):
    agent_id: uuid.UUID | None = Field(default=None)
    role_id: uuid.UUID | None = Field(default=None)


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


class CellMorphology(Block):
    name: str = Field(description="Name of the morphology")
    description: str = Field(description="Description")
    species_id: uuid.UUID | None = Field(default=None)
    strain_id: uuid.UUID | None = Field(default=None)
    brain_region_id: uuid.UUID | None = Field(default=None)


class Subject(Block):
    name: str = Field(..., description="Subject name")
    description: str = Field(..., description="Subject description")
    sex: Annotated[Sex, Field(title="Sex", description="Sex of the subject")] = Sex.unknown
    weight: float | None = Field(
        default=None,
        title="Weight",
        description="Weight in grams",
        gt=0.0,
        json_schema_extra={"default": None},
    )
    age_value: timedelta = Field(
        ...,
        title="Age value",
        description="Age value.",
        gt=timedelta(0),
    )
    age_min: timedelta | None = Field(
        default=None,
        title="Minimum age (of range)",
        description="Minimum age (of range)",
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
    species_id: uuid.UUID = Field(..., description="Species UUID")
    strain_id: uuid.UUID | None = Field(default=None)


class License(Block):
    license_id: uuid.UUID | None = Field(default=None)


class SubjectID(Block):
    subject_id: uuid.UUID | None = Field(default=None)


class ScientificArtifact(Block):
    experiment_date: datetime | None = Field(default=None)
    contact_email: str | None = Field(default=None)
    atlas_id: uuid.UUID | None = Field(default=None)


class ContributeMorphologyScanConfig(ScanConfig):
    """Contribute Morphology ScanConfig."""

    single_coord_class_name: ClassVar[str] = "ContributeMorphologySingleConfig"
    name: ClassVar[str] = "Contribute a Morphology"
    description: ClassVar[str] = "ScanConfig to contribute a morphology to the OBI."

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

    assets: Assets = Field(default_factory=Assets, title="Assets", description="Morphology files.")

    contribution: Contribution = Field(
        default_factory=Contribution, title="Contribution", description="Contributor."
    )

    morphology: CellMorphology = Field(
        default_factory=CellMorphology,
        title="Morphology",
        description="Information about the morphology.",
    )

    publication: Publication = Field(
        default_factory=Publication,
        title="Publication Details",
        description="Publication details.",
    )

    subject: SubjectID = Field(
        default_factory=License,
        title="Subject",
        description="The subject from which the morphology was derived.",
    )

    license: License = Field(
        default_factory=License,
        title="License",
        description="The license used.",
    )

    scientificartifact: ScientificArtifact = Field(
        default_factory=ScientificArtifact,
        title="Scientific Artifact",
        description="Information about the artifact.",
    )

    mtype: MTypeClassification = Field(
        default_factory=MTypeClassification,
        title="Mtype Classification",
        description="The mtype.",
    )


class ContributeMorphologySingleConfig(ContributeMorphologyScanConfig, SingleConfigMixin):
    """Placeholder here to maintain compatibility."""


class ContributeMorphologyTask(Task):
    config: ContributeMorphologySingleConfig

    def execute(
        self, *, db_client: entitysdk.client.Client = None, entity_cache: bool = False
    ) -> None:
        pass


class ContributeSubjectScanConfig(ScanConfig):
    """Contribute Morphology ScanConfig."""

    single_coord_class_name: ClassVar[str] = "ContributeSubjectSingleConfig"
    name: ClassVar[str] = "Contribute a Subject"
    description: ClassVar[str] = "ScanConfig to contribute a subject to the OBI."

    subject: Subject = Field(
        default_factory=Subject,
        title="Subject",
        description="Information about the subject.",
    )


class ContributeSubjectSingleConfig(ContributeMorphologyScanConfig, SingleConfigMixin):
    """Placeholder here to maintain compatibility."""


class ContributeSubjectTask(Task):
    config: ContributeSubjectSingleConfig

    def execute(self, *, db_client: entitysdk.client.Client = None) -> None:
        pass

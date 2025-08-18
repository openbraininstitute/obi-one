import json
import os
from typing import ClassVar, Literal, Self, Annotated

from pydantic import (
    Field,
    PrivateAttr,
    model_validator,
    NonNegativeInt,
    NonNegativeFloat,
    PositiveInt,
    PositiveFloat,
)

from obi_one.core.block import Block
from obi_one.core.constants import (
    _MIN_SIMULATION_LENGTH_MILLISECONDS,
    _MAX_SIMULATION_LENGTH_MILLISECONDS,
)
from obi_one.core.form import Form
from obi_one.core.single import SingleCoordinateMixin
from obi_one.core.info import Info

# from obi_one.core.exception import OBIONE_Error
from obi_one.scientific.circuit.circuit import Circuit
from obi_one.scientific.circuit.neuron_sets import NeuronSet
from obi_one.scientific.unions.unions_extracellular_location_sets import (
    ExtracellularLocationSetUnion,
)
from obi_one.scientific.unions.unions_manipulations import (
    SynapticManipulationsUnion,
    SynapticManipulationsReference,
)
from obi_one.scientific.unions.unions_morphology_locations import MorphologyLocationUnion
from obi_one.scientific.unions.unions_neuron_sets import (
    SimulationNeuronSetUnion,
    NeuronSetReference,
)
from obi_one.scientific.unions.unions_recordings import RecordingUnion, RecordingReference
from obi_one.scientific.unions.unions_stimuli import StimulusUnion, StimulusReference
from obi_one.scientific.unions.unions_synapse_set import SynapseSetUnion
from obi_one.scientific.unions.unions_timestamps import TimestampsUnion, TimestampsReference

from obi_one.database.circuit_from_id import CircuitFromID

import entitysdk
from collections import OrderedDict

from datetime import UTC, datetime

from pathlib import Path

import logging
import uuid

L = logging.getLogger(__name__)

from enum import StrEnum


class BlockGroup(StrEnum):
    """Authentication and authorization errors."""

    SETUP_BLOCK_GROUP = "Setup"
    DENSITY_BLOCK_GROUP = "Morphology files"
    CONTRIBUTOR_BLOCK_GROUP = "Experimenter"
    STRAIN_BLOCK_GROUP = "Animal strain"
    LOCATION_GROUP = "Location"
    PROTOCOL_GROUP = "Protocol"
    LICENSE_GROUP = "License"


from pydantic import BaseModel
from enum import Enum, StrEnum, auto
from datetime import timedelta
from typing import TypedDict, Optional


class Sex(StrEnum):
    male = auto()
    female = auto()
    unknown = auto()


class AgePeriod(StrEnum):
    prenatal = auto()
    postnatal = auto()
    unknown = auto()


class StatusEnum(str, Enum):
    active = "active"
    inactive = "inactive"
    pending = "pending"


class Contribution(BaseModel):
    name: str = Field(default="", description="Contribution name")
    status: StatusEnum = Field(default=StatusEnum.pending, description="Status")


class Author(BaseModel):
    given_name: Optional[str] = None
    family_name: Optional[str] = None


class Reference(BaseModel):
    type: str = Field(..., description="Reference type (e.g. DOI, PubMed)")
    identifier: str = Field(..., description="Unique reference identifier")

    class Config:
        json_schema_extra = {"title": "Reference"}


class Publication(Block):
    name: str = Field(default="", description="Publication name")
    description: str = Field(default="", description="Publication description")
    DOI: Optional[str] = Field(default="")
    publication_title: Optional[str] = Field(default="")
    authors: Optional[Author] = Field(default=None)
    publication_year: Optional[int] = Field(default=None)
    abstract: Optional[str] = Field(default="")
    #  reference: Optional[Reference] = Field(default=None)

    class Config:
        json_schema_extra = {"title": "Publication"}


class MTypeClassification(Block):
    mtype_class_id: uuid.UUID | None = Field(
        default=None, description="UUID for MType classification"
    )


class ETypeClassification(Block):
    etype_class_id: uuid.UUID | None = Field(
        default=None, description="UUID for EType classification"
    )


class ContributeDensityForm(Form):
    """Contribute Density Form."""

    single_coord_class_name: ClassVar[str] = "ContributeDensity"
    name: ClassVar[str] = "Density Contribution"
    description: ClassVar[str] = "Allows the user to contribute a neuron density."

    class Config:
        json_schema_extra = {
            "block_block_group_order": [
                BlockGroup.SETUP_BLOCK_GROUP,
                BlockGroup.CONTRIBUTOR_BLOCK_GROUP,
                BlockGroup.STRAIN_BLOCK_GROUP,
                BlockGroup.LOCATION_GROUP,
                BlockGroup.PROTOCOL_GROUP,
                BlockGroup.LICENSE_GROUP,
            ]
        }

    class Measurements(Block):
        name: str = Field(description="Name of the measurement")  # Add default
        unit: str = Field(description="units", default="1/mm3")
        value: float = Field(description="value of the density")

    class NeuronDensity(Block):
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
        weight: Optional[float] = Field(
            default=None,
            title="Weight",
            description="Weight in grams",
            gt=0.0,
            json_schema_extra={"default": None},  # Ensure default appears in schema
        )
        age_value: Optional[timedelta] = Field(
            default=None, title="Age value", description="Age value interval.", gt=timedelta(0)
        )
        age_min: Optional[timedelta] = Field(
            default=None,
            title="Minimum age range",
            description="Minimum age range",
            gt=timedelta(0),
        )
        age_max: Optional[timedelta] = Field(
            default=None,
            title="Maximum age range",
            description="Maximum age range",
            gt=timedelta(0),
        )
        age_period: AgePeriod | None = AgePeriod.unknown

        model_config = {"extra": "forbid"}

    class License(Block):
        license_id: uuid.UUID | None = Field(default=None)

    class ScientificArtifact(Block):
        # model_config = ConfigDict(from_attributes=True)
        # published_in: str | None = None
        experiment_date: datetime | None = Field(default=None)
        contact_email: str | None = Field(default=None)

    contribution: Contribution = Field(
        default_factory=Contribution,  # ✅ Add this
        title="Contribution",
        description="Contributor.",
        group=BlockGroup.SETUP_BLOCK_GROUP,
        group_order=1,
    )

    neurondensity: NeuronDensity = Field(
        default_factory=NeuronDensity,  # ✅ Add this
        title="Neuron density",
        description="Information about neuron density.",
        group=BlockGroup.SETUP_BLOCK_GROUP,
        group_order=0,
    )

    measurements: Measurements = Field(
        default_factory=Measurements,  # ✅ Add this
        title="Measurements",
        description="The measurement value.",
        group=BlockGroup.SETUP_BLOCK_GROUP,
        group_order=1,
    )

    subject: Subject = Field(
        default_factory=Subject,  # ✅ Add this
        title="Subject",
        description="Information about the subject.",
        group=BlockGroup.CONTRIBUTOR_BLOCK_GROUP,
        group_order=0,
    )

    license: License = Field(
        default_factory=License,  # ✅ Add this
        title="License",
        description="The license used.",
        group=BlockGroup.LICENSE_GROUP,
        group_order=0,
    )

    mtype: MTypeClassification = Field(
        default_factory=MTypeClassification,
        title="Mtype Classification",
        description="The mtype.",
        group=BlockGroup.CONTRIBUTOR_BLOCK_GROUP,
        group_order=0,
    )

    etype: ETypeClassification = Field(
        default_factory=ETypeClassification,
        title="Etype Classification",
        description="The etype.",
        group=BlockGroup.CONTRIBUTOR_BLOCK_GROUP,
        group_order=0,
    )


class ContributeDensity(ContributeDensityForm, SingleCoordinateMixin):
    """Placeholder here to maintain compatibility."""

    CONFIG_FILE_NAME: ClassVar[str] = ""
    NODE_SETS_FILE_NAME: ClassVar[str] = ""

    _sonata_config: dict = PrivateAttr(default={})

    def generate(self, db_client: entitysdk.client.Client = None):
        pass

    def save(
        self, campaign: entitysdk.models.SimulationCampaign, db_client: entitysdk.client.Client
    ) -> None:
        pass

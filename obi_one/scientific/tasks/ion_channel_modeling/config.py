"""Ion channel modeling task configuration."""

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Any, ClassVar, Literal

from entitysdk.client import Client
from entitysdk.models import BrainRegion, Subject
from entitysdk.types import Sex
from pydantic import Discriminator, Field, StringConstraints

from obi_one.core.block import Block
from obi_one.core.exception import ConfigValidationError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.core.units import Units
from obi_one.scientific.blocks.ion_channel_equations.ion_channel_equations import (
    EquationKey,
    equation_schema_extra,
)
from obi_one.scientific.from_id.brain_region_from_id import BrainRegionFromID
from obi_one.scientific.from_id.ion_channel_recording_from_id import IonChannelRecordingFromID
from obi_one.scientific.from_id.species_from_id import SpeciesFromID
from obi_one.scientific.from_id.strain_from_id import StrainFromID
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig

NEURON_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"


def neuron_safe_name(name: str) -> str:
    """A channel name as a NEURON SUFFIX: Kv6.2 gives Kv6_2."""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", name)
    return safe if re.match(r"[A-Za-z_]", safe) else f"_{safe}"


def _id(entity: Any) -> uuid.UUID | None:
    return entity.id if entity is not None else None


def _shared(items: list, what: str, key: Callable = _id, label: Callable = str) -> Any:
    distinct = {key(item): item for item in items}
    if len(distinct) > 1:
        values = ", ".join(sorted(label(item) for item in distinct.values()))
        msg = f"The recordings differ in {what} ({values}), so set the model's {what}."
        raise ConfigValidationError(msg)
    return next(iter(distinct.values()))


def _ancestors(region_id: uuid.UUID, db_client: Client) -> list:
    chain = [db_client.get_entity(entity_id=region_id, entity_type=BrainRegion)]
    while chain[-1].parent_structure_id:
        chain.append(
            db_client.get_entity(entity_id=chain[-1].parent_structure_id, entity_type=BrainRegion)
        )
    return chain


def common_parent_region(regions: list, db_client: Client) -> Any:
    """The deepest region that contains every one of the regions."""
    region_ids = list(dict.fromkeys(region.id for region in regions))
    if len(region_ids) == 1:
        return regions[0]
    chains = [_ancestors(region_id, db_client) for region_id in region_ids]
    in_all = set.intersection(*({region.id for region in chain} for chain in chains))
    for region in chains[0]:
        if region.id in in_all:
            return region
    msg = "The recordings' brain regions have no common parent, so set the model's brain region."
    raise ConfigValidationError(msg)


def generic_subject(species: Any, strain: Any, db_client: Client) -> Any:
    """The `Generic <species>[/<strain>]` subject, registered in the project when there is none."""
    name = f"Generic {species.name}" + (f"/{strain.name}" if strain else "")
    for subject in db_client.search_entity(entity_type=Subject, query={"name": name}):
        if subject.species.id == species.id and _id(subject.strain) == _id(strain):
            return subject
    return db_client.register_entity(
        Subject(
            name=name,
            description=f"Subject for models of {species.name} built from several subjects.",
            sex=Sex.unknown,
            species=species,
            strain=strain,
        )
    )


@dataclass(frozen=True)
class ResolvedModelProperties:
    ion_channel_name: str
    temperature: float | None
    species: Any
    strain: Any
    brain_region: Any
    # The recordings' own subject, when they share one with this species and strain.
    subject: Any


class IonChannelModelProperties(Block):
    """What the fitted model is registered with. An unset property comes from the recordings."""

    ion_channel_name: Annotated[str, StringConstraints(pattern=NEURON_NAME_PATTERN)] | None = Field(
        default=None,
        title="Ion channel name",
        description=(
            "SUFFIX of the mod file. Unset: the recordings' channel, so Kv6.2 gives Kv6_2. "
            "Must start with a letter or underscore, and contain only letters, numbers and "
            "underscores."
        ),
    )
    temperature: float | None = Field(
        default=None,
        title="Temperature",
        description="Temperature of the model, in °C. Unset: the recordings' temperature.",
        json_schema_extra={SchemaKey.UNITS: Units.CELSIUS},
    )
    species: SpeciesFromID | None = Field(
        default=None,
        title="Species",
        description="Species of the model. Unset: the recordings' species.",
    )
    strain: StrainFromID | None = Field(
        default=None,
        title="Strain",
        description=(
            "Strain of the model, of its species. Unset: the strain of the recordings of that "
            "species, if any."
        ),
    )
    brain_region: BrainRegionFromID | None = Field(
        default=None,
        title="Brain region",
        description=(
            "Brain region of the model. Unset: the deepest region containing all the "
            "recordings' regions."
        ),
    )


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    MODEL = "Model"


class HodgkinHuxleyIonChannelModel(Block):
    """The channel model to fit: one equation per gating variable, plus their exponents."""

    title: ClassVar[str] = "Hodgkin-Huxley ion channel model"

    m_power: Annotated[int, Field(ge=1, le=4)] | list[Annotated[int, Field(ge=1, le=4)]] = Field(
        title=r"$m$ exponent in channel equation",
        default=1,
        description=(
            r"Exponent $p$ of $m$ in the channel equation: "
            r"$g = \bar{g} \cdot m^p \cdot h^q$"
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    h_power: Annotated[int, Field(ge=0, le=4)] | list[Annotated[int, Field(ge=0, le=4)]] = Field(
        title=r"$h$ exponent in channel equation",
        default=1,
        description=(
            r"Exponent $q$ of $h$ in the channel equation: "
            r"$g = \bar{g} \cdot m^p \cdot h^q$"
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )

    minf_eq: Literal[EquationKey.SIG_FIT_MINF] = Field(
        title=r"$m_\infty$ equation",
        description=(
            r"Steady state activation parameter $m_{\infty}$ equation. "
            r"This equation will be used for solving the differential equation: "
            r"$\frac{dm}{dt} = \frac{m_{\infty} - m}{\tau_{m}}$"
        ),
        default=EquationKey.SIG_FIT_MINF,
        json_schema_extra=equation_schema_extra,
    )

    mtau_eq: Literal[
        EquationKey.SIG_FIT_MTAU,
        EquationKey.THERMO_FIT_MTAU,
        EquationKey.THERMO_FIT_MTAU_V2,
        EquationKey.BELL_FIT_MTAU,
    ] = Field(
        title=r"$\tau_m$ equation",
        description=(
            r"Activation time constant $\tau_m$ equation. "
            r"This equation will be used for solving the differential equation: "
            r"$\frac{dm}{dt} = \frac{m_{\infty} - m}{\tau_{m}}$"
        ),
        default=EquationKey.SIG_FIT_MTAU,
        json_schema_extra=equation_schema_extra,
    )

    hinf_eq: Literal[EquationKey.SIG_FIT_HINF] = Field(
        title=r"$h_\infty$ equation",
        description=(
            r"Steady state inactivation parameter $h_{\infty}$ equation. "
            r"This equation will be used for solving the differential equation: "
            r"$\frac{dh}{dt} = \frac{h_{\infty} - h}{\tau_{h}}$"
        ),
        default=EquationKey.SIG_FIT_HINF,
        json_schema_extra=equation_schema_extra,
    )

    htau_eq: Literal[EquationKey.SIG_FIT_HTAU] = Field(
        title=r"$\tau_h$ equation",
        description=(
            r"Inactivation time constant $\tau_h$ equation. "
            r"This equation will be used for solving the differential equation: "
            r"$\frac{dh}{dt} = \frac{h_{\infty} - h}{\tau_{h}}$"
        ),
        default=EquationKey.SIG_FIT_HTAU,
        json_schema_extra=equation_schema_extra,
    )


# One member, but a discriminated union rather than a bare block: the editor draws it as a
# block_union, so a second channel formalism becomes another member and nothing else changes.
IonChannelModelUnion = Annotated[HodgkinHuxleyIonChannelModel, Discriminator("type")]


class IonChannelFittingScanConfig(InfoScanConfig):
    """Form for modeling an ion channel model from a set of ion channel traces."""

    name: ClassVar[str] = "Ion channel"
    description: ClassVar[str] = "Models ion channel model from a set of ion channel traces."

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP,
            BlockGroup.MODEL,
        ],
    }

    class Initialize(Block):
        recordings: tuple[IonChannelRecordingFromID, ...] = Field(
            title="Ion channel recordings",
            description=(
                "The recordings to fit the channel model to, up to 3. Several are fitted "
                "jointly into one model, not one model each."
            ),
            min_length=1,
            max_length=3,
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER_MULTIPLE},
        )

        model_properties: IonChannelModelProperties = Field(
            default=IonChannelModelProperties(),
            title="Model properties",
            description=(
                "The channel name, temperature, species, strain and brain region the model is "
                "registered with. Each defaults to the recordings' value; set it when they "
                "differ, or to change it."
            ),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.ION_CHANNEL_MODEL_PROPERTIES},
        )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the fitting.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    model_type: IonChannelModelUnion = Field(
        title="Ion channel model",
        description=(
            "The Hodgkin-Huxley channel model to fit: an equation per gating variable, and "
            r"the exponents $p$ and $q$ of $m$ and $h$ in the channel equation "
            r"$g = \bar{g} \cdot m^p \cdot h^q$."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_UNION,
            SchemaKey.GROUP: BlockGroup.MODEL,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    def input_entities(self, db_client: Client) -> list:
        entities = [
            recording.entity(db_client=db_client) for recording in self.initialize.recordings
        ]
        # Fails at generation, before anything is registered, when a property can't be resolved.
        self.resolve_model_properties(entities, db_client=db_client)
        return entities

    def resolve_model_properties(
        self, recordings: list, db_client: Client
    ) -> ResolvedModelProperties:
        given = self.initialize.model_properties

        ion_channel_name = given.ion_channel_name or neuron_safe_name(
            _shared(
                [recording.ion_channel for recording in recordings],
                "ion channel",
                label=lambda channel: channel.name,
            ).name
        )
        temperature = (
            given.temperature
            if given.temperature is not None
            else _shared(
                [recording.temperature for recording in recordings],
                "temperature",
                key=lambda temperature: temperature,
                label=lambda temperature: "none" if temperature is None else f"{temperature} °C",
            )
        )
        species: Any = (
            given.species.entity(db_client=db_client)
            if given.species
            else _shared(
                [recording.subject.species for recording in recordings],
                "species",
                label=lambda species: species.name,
            )
        )
        if given.strain:
            strain = given.strain.entity(db_client=db_client)
        else:
            strains = [
                recording.subject.strain
                for recording in recordings
                if recording.subject.species.id == species.id
            ]
            strain = (
                _shared(
                    strains,
                    "strain",
                    label=lambda strain: strain.name if strain else "no strain",
                )
                if strains
                else None
            )
        if strain and strain.species_id != species.id:
            msg = f"Strain {strain.name} is not a strain of {species.name}."
            raise ConfigValidationError(msg)
        brain_region = (
            given.brain_region.entity(db_client=db_client)
            if given.brain_region
            else common_parent_region(
                [recording.brain_region for recording in recordings], db_client=db_client
            )
        )

        subjects = {recording.subject.id: recording.subject for recording in recordings}
        subject = next(iter(subjects.values())) if len(subjects) == 1 else None
        if subject and (subject.species.id != species.id or _id(subject.strain) != _id(strain)):
            subject = None

        return ResolvedModelProperties(
            ion_channel_name=ion_channel_name,
            temperature=temperature,
            species=species,
            strain=strain,
            brain_region=brain_region,
            subject=subject,
        )


class IonChannelFittingSingleConfig(IonChannelFittingScanConfig, SingleConfigMixin):
    """Only allows single values and ensures nested attributes follow the same rule."""

"""Pydantic definitions for BluePyEModel section-list choices and aliases."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AxonModifier(StrEnum):
    """Allowlisted BluePyEModel morphology modifier names."""

    REPLACE_AXON_WITH_TAPER = "replace_axon_with_taper"
    REPLACE_AXON_LEGACY = "replace_axon_legacy"
    REPLACE_AXON_OLFACTORY_BULB = "replace_axon_olfactory_bulb"
    BLUEPYOPT_REPLACE_AXON = "bluepyopt_replace_axon"
    NONE = "none"


class SectionListAvailability(StrEnum):
    """Availability state exposed to the form for a section-list choice."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


type PhysicalSectionListName = Literal[
    "somatic",
    "basal",
    "apical",
    "axonal",
    "myelinated",
]

type SectionListName = Literal[
    "all",
    "alldend",
    "somadend",
    "allnoaxon",
    "somaxon",
    "allact",
    "somatic",
    "basal",
    "apical",
    "axonal",
    "myelinated",
]

type RegionalSectionListName = SectionListName

PHYSICAL_SECTION_LIST_NAMES: tuple[PhysicalSectionListName, ...] = (
    "somatic",
    "basal",
    "apical",
    "axonal",
    "myelinated",
)

REGIONAL_SECTION_LIST_NAMES: tuple[RegionalSectionListName, ...] = (
    "all",
    "alldend",
    "somadend",
    "allnoaxon",
    "somaxon",
    "allact",
    *PHYSICAL_SECTION_LIST_NAMES,
)

AXON_MODIFIER_DESCRIPTIONS: dict[str, str] = {
    AxonModifier.REPLACE_AXON_WITH_TAPER.value: (
        "Replace the source axon with a tapered AIS and one synthesized myelin section."
    ),
    AxonModifier.REPLACE_AXON_LEGACY.value: (
        "Use the legacy two-section axon replacement without synthesized myelin."
    ),
    AxonModifier.REPLACE_AXON_OLFACTORY_BULB.value: (
        "Use the olfactory-bulb hillock, node, and myelin replacement."
    ),
    AxonModifier.BLUEPYOPT_REPLACE_AXON.value: (
        "Use BluePyOpt's built-in two-section axon replacement without synthesized myelin."
    ),
    AxonModifier.NONE.value: (
        "Keep the imported morphology without an axon replacement; source myelination is unknown."
    ),
}


_COMPOSITE_SECTION_COUNT = 2


class SectionListDefinition(BaseModel):
    """Validated definition of one primitive or composite section-list choice."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: SectionListName = Field(title="Section-list name")
    label: str = Field(title="Section-list label")
    description: str = Field(title="Section-list description")
    expanded_sections: tuple[PhysicalSectionListName, ...] = Field(
        title="Expanded section lists",
        description="Concrete NEURON section lists used by the BluePyEModel alias.",
    )
    is_composite: bool = Field(
        default=False,
        title="Composite section list",
        description="Whether this name expands to more than one concrete section list.",
    )
    requires_myelinated: bool = Field(
        default=False,
        title="Requires myelinated sections",
        description="Whether the choice requires a synthesized or source myelinated list.",
    )
    display_order: int = Field(
        default=0,
        title="Display order",
        description=(
            "Position of this choice in the form's region-card list. Independent from "
            "compilation order, which is always broad-to-narrow."
        ),
    )

    @model_validator(mode="after")
    def validate_expansion(self) -> SectionListDefinition:
        """Ensure aliases have stable, non-empty, non-duplicated expansions."""
        if not self.expanded_sections:
            msg = f"Section-list '{self.name}' must expand to at least one section list."
            raise ValueError(msg)
        if len(set(self.expanded_sections)) != len(self.expanded_sections):
            msg = f"Section-list '{self.name}' contains duplicate expanded section lists."
            raise ValueError(msg)
        if self.is_composite and len(self.expanded_sections) < _COMPOSITE_SECTION_COUNT:
            msg = f"Composite section-list '{self.name}' must expand to multiple section lists."
            raise ValueError(msg)
        if self.name == "myelinated" and self.expanded_sections != ("myelinated",):
            msg = "The myelinated section list may only expand to itself."
            raise ValueError(msg)
        if self.requires_myelinated and "myelinated" not in self.expanded_sections:
            msg = f"Section-list '{self.name}' is marked as requiring myelinated sections."
            raise ValueError(msg)
        if "myelinated" in self.expanded_sections and self.name != "myelinated":
            msg = "Combined section-list aliases must not contain myelinated sections."
            raise ValueError(msg)
        return self


class SectionListChoice(BaseModel):
    """A section-list definition annotated for form availability."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: SectionListName = Field(title="Section-list name")
    label: str = Field(title="Section-list label")
    description: str = Field(title="Section-list description")
    available: bool = Field(
        default=True,
        title="Available",
        description="Whether the form may use this section list for the current modifier.",
    )
    availability: SectionListAvailability = Field(
        default=SectionListAvailability.AVAILABLE,
        title="Availability",
        description="Whether availability is known, unavailable, or dependent on source data.",
    )
    disabled_reason: str | None = Field(
        default=None,
        title="Disabled reason",
        description="Reason shown when a section list is not selectable.",
    )
    display_order: int = Field(
        default=0,
        title="Display order",
        description="Position of this choice in the form's region-card list.",
    )

    @model_validator(mode="after")
    def validate_availability(self) -> SectionListChoice:
        """Keep the boolean and descriptive availability state consistent."""
        if self.available and self.availability == SectionListAvailability.UNAVAILABLE:
            msg = f"Available section-list '{self.name}' cannot have unavailable status."
            raise ValueError(msg)
        if not self.available and self.availability != SectionListAvailability.UNAVAILABLE:
            msg = f"Unavailable section-list '{self.name}' must have unavailable status."
            raise ValueError(msg)
        if self.available and self.disabled_reason is not None:
            msg = f"Available section-list '{self.name}' cannot have a disabled reason."
            raise ValueError(msg)
        if not self.available and not self.disabled_reason:
            msg = f"Unavailable section-list '{self.name}' needs a disabled reason."
            raise ValueError(msg)
        return self

    @property
    def enabled(self) -> bool:
        """Alias used by form clients that call selectable choices enabled."""
        return self.available


def _default_section_list_definitions() -> tuple[SectionListDefinition, ...]:
    """Construct the canonical definitions after the model class is available."""
    return _make_default_section_list_definitions()


class SectionListCatalog(BaseModel):
    """Immutable, validated catalogue of primitive and composite section lists."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    definitions: tuple[SectionListDefinition, ...] = Field(
        default_factory=_default_section_list_definitions,
        title="Section-list definitions",
        description="Canonical BluePyEModel section-list names and alias expansions.",
    )

    @model_validator(mode="after")
    def validate_catalog(self) -> SectionListCatalog:
        """Require exactly one definition for every canonical section-list name."""
        names = tuple(definition.name for definition in self.definitions)
        if len(set(names)) != len(names):
            msg = "Section-list catalog definitions must have unique names."
            raise ValueError(msg)
        missing = set(REGIONAL_SECTION_LIST_NAMES) - set(names)
        if missing:
            msg = f"Section-list catalog is missing definitions: {sorted(missing)}."
            raise ValueError(msg)
        return self

    def definition(self, name: SectionListName) -> SectionListDefinition:
        """Return the validated definition for a section-list name."""
        for definition in self.definitions:
            if definition.name == name:
                return definition
        msg = f"Unsupported section-list name: {name}."
        raise ValueError(msg)

    def expand(self, name: SectionListName) -> tuple[PhysicalSectionListName, ...]:
        """Expand a canonical name into concrete NEURON section-list names."""
        return self.definition(name).expanded_sections

    def choice(
        self,
        name: SectionListName,
        *,
        axon_modifier: AxonModifier | str = AxonModifier.REPLACE_AXON_WITH_TAPER,
    ) -> SectionListChoice:
        """Return one form choice with modifier-specific myelin availability."""
        definition = self.definition(name)
        if name != "myelinated":
            return SectionListChoice(
                name=definition.name,
                label=definition.label,
                description=definition.description,
                display_order=definition.display_order,
            )

        modifier = AxonModifier(axon_modifier)
        if modifier in {
            AxonModifier.REPLACE_AXON_LEGACY,
            AxonModifier.BLUEPYOPT_REPLACE_AXON,
        }:
            return SectionListChoice(
                name=definition.name,
                label=definition.label,
                description=definition.description,
                available=False,
                availability=SectionListAvailability.UNAVAILABLE,
                disabled_reason=(
                    f"The '{modifier.value}' modifier does not create a myelinated section list."
                ),
                display_order=definition.display_order,
            )
        if modifier == AxonModifier.NONE:
            return SectionListChoice(
                name=definition.name,
                label=definition.label,
                description=(
                    f"{definition.description} The source morphology may or may not provide it; "
                    "this first-release form does not inspect the morphology asset."
                ),
                available=False,
                availability=SectionListAvailability.UNAVAILABLE,
                disabled_reason=(
                    "No replacement leaves source myelination unknown, so the myelinated "
                    "section list is unavailable without morphology preflight."
                ),
                display_order=definition.display_order,
            )
        return SectionListChoice(
            name=definition.name,
            label=definition.label,
            description=definition.description,
            display_order=definition.display_order,
        )

    def choices(
        self,
        *,
        axon_modifier: AxonModifier | str = AxonModifier.REPLACE_AXON_WITH_TAPER,
    ) -> tuple[SectionListChoice, ...]:
        """Return all canonical choices in stable catalogue order."""
        return tuple(
            self.choice(definition.name, axon_modifier=axon_modifier)
            for definition in self.definitions
        )

    def available(
        self,
        name: SectionListName,
        *,
        axon_modifier: AxonModifier | str = AxonModifier.REPLACE_AXON_WITH_TAPER,
    ) -> bool:
        """Return whether a section-list choice can be selected for a modifier."""
        return self.choice(name, axon_modifier=axon_modifier).available

    def schema_choices(self) -> list[dict[str, object]]:
        """Return Pydantic-validated choice metadata for the default modifier."""
        return [choice.model_dump(mode="json") for choice in self.choices()]

    def schema_availability_by_modifier(self) -> dict[str, list[dict[str, object]]]:
        """Return validated choices for every allowlisted axon modifier."""
        return {
            modifier.value: [
                choice.model_dump(mode="json") for choice in self.choices(axon_modifier=modifier)
            ]
            for modifier in AxonModifier
        }

    def to_recipe_multiloc_map(self) -> dict[str, list[str]]:
        """Build the BluePyEModel recipe map from validated alias definitions."""
        return {
            definition.name: list(definition.expanded_sections)
            for definition in self.definitions
            if definition.is_composite
        }


def _make_default_section_list_definitions() -> tuple[SectionListDefinition, ...]:
    return (
        SectionListDefinition(
            name="all",
            label="All sections",
            description="Apical, basal, somatic, and axonal sections.",
            expanded_sections=("apical", "basal", "somatic", "axonal"),
            is_composite=True,
            display_order=0,
        ),
        SectionListDefinition(
            name="myelinated",
            label="Myelinated",
            description="Myelinated sections created by a compatible axon modifier.",
            expanded_sections=("myelinated",),
            requires_myelinated=True,
            display_order=1,
        ),
        SectionListDefinition(
            name="somadend",
            label="Soma and dendrites",
            description="Apical, basal, and somatic sections.",
            expanded_sections=("apical", "basal", "somatic"),
            is_composite=True,
            display_order=2,
        ),
        SectionListDefinition(
            name="somatic",
            label="Somatic",
            description="Somatic sections only.",
            expanded_sections=("somatic",),
            display_order=3,
        ),
        SectionListDefinition(
            name="axonal",
            label="Axonal",
            description="Axonal sections only.",
            expanded_sections=("axonal",),
            display_order=4,
        ),
        SectionListDefinition(
            name="apical",
            label="Apical",
            description="Apical dendritic sections only.",
            expanded_sections=("apical",),
            display_order=5,
        ),
        SectionListDefinition(
            name="basal",
            label="Basal",
            description="Basal dendritic sections only.",
            expanded_sections=("basal",),
            display_order=6,
        ),
        SectionListDefinition(
            name="alldend",
            label="All dendrites",
            description="Apical and basal dendritic sections.",
            expanded_sections=("apical", "basal"),
            is_composite=True,
            display_order=7,
        ),
        SectionListDefinition(
            name="allnoaxon",
            label="All sections without axon",
            description="Apical, basal, and somatic sections.",
            expanded_sections=("apical", "basal", "somatic"),
            is_composite=True,
            display_order=8,
        ),
        SectionListDefinition(
            name="somaxon",
            label="Soma and axon",
            description="Axonal and somatic sections.",
            expanded_sections=("axonal", "somatic"),
            is_composite=True,
            display_order=9,
        ),
        SectionListDefinition(
            name="allact",
            label="All active sections",
            description="Apical, basal, somatic, and axonal sections for active mechanisms.",
            expanded_sections=("apical", "basal", "somatic", "axonal"),
            is_composite=True,
            display_order=10,
        ),
    )


DEFAULT_SECTION_LIST_CATALOG = SectionListCatalog()


def default_section_list_catalog() -> SectionListCatalog:
    """Return the canonical immutable section-list catalogue."""
    return DEFAULT_SECTION_LIST_CATALOG

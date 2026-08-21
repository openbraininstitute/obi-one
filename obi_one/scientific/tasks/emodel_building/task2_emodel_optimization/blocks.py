"""Blocks for the 02_emodel_optimization stage."""

import math
from collections.abc import Mapping
from typing import Annotated, Any, ClassVar, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    model_validator,
)

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.from_id.etype_class_from_id import ETypeClassFromID
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.section_lists import (
    AXON_MODIFIER_DESCRIPTIONS,
    DEFAULT_SECTION_LIST_CATALOG,
    REGIONAL_SECTION_LIST_NAMES,
    AxonModifier,
    RegionalSectionListName,
    SectionListChoice,
    SectionListName,
)


class DistanceDependentDistribution(Block):
    """A BluePyEModel distance-dependent parameter transformation."""

    name: str | None = Field(
        default=None,
        min_length=1,
        title="Distribution name",
        description="Optional name used by BluePyEModel parameter definitions.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    function: str | None = Field(
        default=None,
        title="Distance function",
        description=(
            "Expression using {value} and {distance}; custom expressions may also use "
            "placeholders defined by the corresponding parameter configuration."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    soma_ref_location: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        title="Soma reference location",
        description="Reference location of the soma along the morphology.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    parameters: tuple[str, ...] | None = Field(
        default=None,
        title="Distribution parameters",
        description=(
            "Names of additional parameters that parametrize the function "
            "(excluding {value} and {distance}). Used by BluePyEModel's "
            "ParameterScaler."
        ),
    )

    @model_validator(mode="after")
    def validate_function(self) -> "DistanceDependentDistribution":
        """Require functions to expose implicit and declared inputs.

        This only checks placeholder presence; it is not an AST validator or a
        sandbox. BluePyEModel evaluates the function string with Python ``eval()``
        at runtime (see ``bluepyemodel.model.model.define_distributions()``), so
        this validator must never be described as a security boundary.
        """
        if self.parameters and self.function is None:
            msg = "Distance-dependent distributions with parameters must define a function."
            raise ValueError(msg)
        if self.function is not None and "{value}" not in self.function:
            msg = "Distance-dependent functions must contain the {value} placeholder."
            raise ValueError(msg)
        if self.function is not None and "{distance}" not in self.function:
            msg = "Distance-dependent functions must contain the {distance} placeholder."
            raise ValueError(msg)
        if self.function is not None:
            for parameter in self.parameters or []:
                placeholder = f"{{{parameter}}}"
                if placeholder not in self.function:
                    msg = (
                        f"Distance-dependent functions must contain the {placeholder} placeholder."
                    )
                    raise ValueError(msg)
        return self

    def to_emc_dict(self, name: str | None = None) -> dict[str, Any]:
        """Convert the block to the legacy EMC distribution representation."""
        emc_dict: dict[str, Any] = {
            "name": name or self.name,
            "function": self.function,
            "soma_ref_location": self.soma_ref_location,
        }
        if self.parameters:
            emc_dict["parameters"] = list(self.parameters)
        return emc_dict


class UniformDistanceDependentDistribution(DistanceDependentDistribution):
    """Default uniform distance distribution used by EMC files."""

    name: str = Field(default="uniform", frozen=True)
    function: None = Field(default=None, frozen=True)


class ExponentialDistanceDependentDistribution(DistanceDependentDistribution):
    """Standard exponential distance distribution used by SSCX and thalamus EMC files."""

    name: str = Field(default="exp", frozen=True)
    function: str = Field(
        default="(-0.8696 + 2.087*math.exp(({distance})*0.0031))*{value}",
        frozen=True,
    )


class StepDistanceDependentDistribution(DistanceDependentDistribution):
    """Step distance distribution used by detailed SSCX models.

    ``{step_begin}`` and ``{step_end}`` are not user-declared placeholders.
    BluePyEModel's ``define_distributions()`` special-cases the name ``step`` and
    computes both values from the imported morphology's calcium hot-spot via
    ``get_hotspot_location()`` (Larkum & Zhu, 2002). Do not add them to
    ``parameters``; they must remain in the function string verbatim.
    """

    name: str = Field(default="step", frozen=True)
    function: str = Field(
        default="{value} * (0.1 + 0.9 * int(({distance} > {step_begin}) & "
        "({distance} < {step_end})))",
        frozen=True,
    )


class ExponentialNaDendDistanceDependentDistribution(DistanceDependentDistribution):
    """Exponential dendritic sodium distance distribution used by hippocampus models."""

    name: str = Field(default="exp_na_dend", frozen=True)
    function: str = Field(default="math.exp((-{distance})/50)*{value}", frozen=True)


class LinearHDApicDistanceDependentDistribution(DistanceDependentDistribution):
    """Linear h-current apical distance distribution used by hippocampus models."""

    name: str = Field(default="linear_hd_apic", frozen=True)
    function: str = Field(default="(1. + 3./100. * {distance})*{value}", frozen=True)


class SigmoidKADApicDistanceDependentDistribution(DistanceDependentDistribution):
    """Sigmoid potassium A-current apical distance distribution."""

    name: str = Field(default="sigmoid_kad_apic", frozen=True)
    function: str = Field(
        default="(15./(1. + math.exp((300-{distance})/50)))*{value}",
        frozen=True,
    )


class LinearEPasApicDistanceDependentDistribution(DistanceDependentDistribution):
    """Linear passive reversal-potential apical distance distribution."""

    name: str = Field(default="linear_e_pas_apic", frozen=True)
    function: str = Field(default="({value}-5*{distance}/150)", frozen=True)


class LinearHDPasDistanceDependentDistribution(DistanceDependentDistribution):
    """Linear h-current passive distance distribution used by mouse models."""

    name: str = Field(default="linear_hdpas", frozen=True)
    function: str = Field(default="(1. + 3./100. * {distance})*{value}", frozen=True)


class SigmoidKADDistanceDependentDistribution(DistanceDependentDistribution):
    """Sigmoid potassium A-current distance distribution used by mouse models."""

    name: str = Field(default="sigmoid_kad", frozen=True)
    function: str = Field(
        default="(15./(1. + math.exp((150-{distance})/10)))*{value}",
        frozen=True,
    )


class SigmoidKDBMApicDistanceDependentDistribution(DistanceDependentDistribution):
    """Sigmoid potassium D-type apical distance distribution used by mouse models."""

    name: str = Field(default="sigmoid_kdbm_apic", frozen=True)
    function: str = Field(
        default="(15./(1. + math.exp(({distance}-50)/50)))*{value}",
        frozen=True,
    )


class CustomDistanceDependentDistribution(DistanceDependentDistribution):
    """User-defined distance-dependent distribution for the optimization workflow."""

    title: ClassVar[str] = "Custom Distance-Dependent Distribution"
    function: str = Field(
        min_length=1,
        title="Custom distance function",
        description="Python expression containing at least {value} and {distance}.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )


DistanceDependentDistributionUnion = Annotated[
    UniformDistanceDependentDistribution
    | ExponentialDistanceDependentDistribution
    | StepDistanceDependentDistribution
    | ExponentialNaDendDistanceDependentDistribution
    | LinearHDApicDistanceDependentDistribution
    | SigmoidKADApicDistanceDependentDistribution
    | LinearEPasApicDistanceDependentDistribution
    | LinearHDPasDistanceDependentDistribution
    | SigmoidKADDistanceDependentDistribution
    | SigmoidKDBMApicDistanceDependentDistribution
    | CustomDistanceDependentDistribution,
    Discriminator("type"),
]


class OptimizationInitialize(Block):
    """Entity-based inputs for the optimisation stage's Setup > Initialization card."""

    emodel: str = Field(
        title="E-Model name",
        description="Top-level key in ``recipes.json`` to operate on (e.g. ``L5PC``).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    etype: ETypeClassFromID = Field(
        title="E-type",
        description="Electrical type entity selected from the database.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.MODEL_SELECTOR_SINGLE,
            SchemaKey.ENTITY_QUERY: {
                "type": "etype",
            },
        },
    )


def default_distance_dependent_distributions() -> dict[str, CustomDistanceDependentDistribution]:
    """Custom distance-dependent distributions declared by the user (empty by default).

    The ten legacy distributions are always selectable by name from
    ``STANDARD_DISTANCE_DEPENDENT_DISTRIBUTIONS`` without being declared here; this
    dict only holds user-defined distributions (see ``CustomDistanceDependentDistribution``).
    """
    return {}


STANDARD_DISTANCE_DEPENDENT_DISTRIBUTIONS: dict[str, DistanceDependentDistributionUnion] = {
    "uniform": UniformDistanceDependentDistribution(),
    "exp": ExponentialDistanceDependentDistribution(),
    "step": StepDistanceDependentDistribution(),
    "exp_na_dend": ExponentialNaDendDistanceDependentDistribution(),
    "linear_hd_apic": LinearHDApicDistanceDependentDistribution(),
    "sigmoid_kad_apic": SigmoidKADApicDistanceDependentDistribution(),
    "linear_e_pas_apic": LinearEPasApicDistanceDependentDistribution(),
    "linear_hdpas": LinearHDPasDistanceDependentDistribution(),
    "sigmoid_kad": SigmoidKADDistanceDependentDistribution(),
    "sigmoid_kdbm_apic": SigmoidKDBMApicDistanceDependentDistribution(),
}
"""Built-in legacy distance-dependent distributions, selectable by name on any parameter row
without being declared in the config's ``distance_dependent_distributions`` field. That field
is reserved for user-defined (``CustomDistanceDependentDistribution``) distributions only."""


def resolve_distance_dependent_distribution(
    name: str,
    custom_distributions: Mapping[str, "CustomDistanceDependentDistribution"],
) -> DistanceDependentDistributionUnion | None:
    """Resolve a distribution name against the standard catalog, then custom declarations."""
    standard = STANDARD_DISTANCE_DEPENDENT_DISTRIBUTIONS.get(name)
    if standard is not None:
        return standard
    return custom_distributions.get(name)


# The Figma "Mechanisms" card is a 3-step wizard. All three steps share the
# "Mechanisms" GROUP (see BlockGroup.INPUTS in config.py); STEP/STEP_ORDER order
# sub-steps within that one group. Distribution selection happens per parameter
# row (see `ParameterSelection.distribution`) against the combined standard +
# custom distribution catalog, so it is not a wizard sub-step of its own.
MECHANISM_SELECTION_STEP = "Mechanism Selection"
REGION_ASSIGNMENT_STEP = "Region assignment"
PARAMETERS_SELECTION_STEP = "Parameters selection"
MECHANISMS_WIZARD_STEPS: tuple[str, ...] = (
    MECHANISM_SELECTION_STEP,
    REGION_ASSIGNMENT_STEP,
    PARAMETERS_SELECTION_STEP,
)


ParameterLocation = Literal["global"] | SectionListName

REGIONAL_PARAMETER_LOCATIONS: frozenset[RegionalSectionListName] = frozenset(
    REGIONAL_SECTION_LIST_NAMES
)


class OptimizationValue(Block):
    """A fixed value or an optimizable lower/upper bound pair."""

    mode: Literal["fixed", "bounds"] = Field(
        default="fixed",
        title="Value mode",
        description="Choose a fixed value or an optimizable interval.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    value: float | None = Field(
        default=None,
        title="Fixed value",
        description="Value used when the mode is fixed.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    bounds: tuple[float, float] | None = Field(
        default=None,
        title="Optimization bounds",
        description=(
            "Lower and upper bounds used when the mode is bounds. If omitted, "
            "the compiler may use an approved type-specific fallback."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    @model_validator(mode="after")
    def validate_mode(self) -> "OptimizationValue":
        """Keep fixed values and bounds mutually exclusive and finite."""
        if self.value is not None and not math.isfinite(self.value):
            msg = "Optimization values must be finite."
            raise ValueError(msg)
        if self.bounds is not None:
            if any(not math.isfinite(bound) for bound in self.bounds):
                msg = "Optimization bounds must be finite."
                raise ValueError(msg)
            if self.bounds[0] > self.bounds[1]:
                msg = "Optimization lower bound must not exceed the upper bound."
                raise ValueError(msg)
        if self.mode == "fixed":
            if self.value is None:
                msg = "A fixed optimization value is required when mode is 'fixed'."
                raise ValueError(msg)
            if self.bounds is not None:
                msg = "Bounds cannot be provided when mode is 'fixed'."
                raise ValueError(msg)
        elif self.value is not None:
            msg = "A fixed value cannot be provided when mode is 'bounds'."
            raise ValueError(msg)
        return self


class ParameterSelection(Block):
    """Value and distance-distribution selection for one regional parameter."""

    value: OptimizationValue
    distribution: str = Field(
        default="uniform",
        min_length=1,
        title="Distance distribution",
        description=(
            "Reusable distance-dependent distribution applied to this regional parameter. "
            "Uniform is the default."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )


class GlobalParameterSelection(Block):
    """Value selection for a global parameter."""

    value: OptimizationValue
    ion_channel_model: IonChannelModelFromID | None = Field(
        default=None,
        title="Ion channel model",
        description="Optional source entity when the global variable belongs to a mechanism.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER},
    )


ParameterGroupKind = Literal["global", "distribution", "region"]


class ParameterRowView(BaseModel):
    """One editable row inside a parameter group, shaped for the Figma parameter cards."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group_key: str
    kind: ParameterGroupKind
    key: str
    name: str
    value: OptimizationValue
    location: str
    mechanism: str | None = None
    distribution: str | None = None
    ion_channel_model: IonChannelModelFromID | None = None
    editable: bool = True


class ParameterGroupView(BaseModel):
    """One card in the Figma "Parameters grouped by region" list.

    Groups are always ``global``, then ``distribution``, then regions in the
    section-list catalog's display order. This mirrors the Figma step-4A
    layout, where ``Global`` and ``Distribution parameters`` are separate
    cards, not a single merged list.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    kind: ParameterGroupKind
    label: str
    description: str
    order: int
    item_count: int
    count_label: str
    section_lists: tuple[SectionListName, ...] | None = None


class MechanismRegionSelection(Block):
    """One IonChannelModel assigned to a morphology region."""

    ion_channel_model: IonChannelModelFromID = Field(
        title="Ion channel model",
        description="IonChannelModel entity whose mechanism is active in this region.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_SELECTOR_SINGLE},
    )
    parameters: dict[str, ParameterSelection] = Field(
        default_factory=dict,
        title="Mechanism parameters",
        description="All selected NMODL variables and their values for this region.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.SINGULAR_NAME: "Mechanism Parameter",
        },
    )


class MorphologySettings(Block):
    """Morphology transformation settings used by BluePyEModel."""

    axon_modifier: AxonModifier = Field(
        default=AxonModifier.REPLACE_AXON_WITH_TAPER,
        title="Axon replacement",
        description=(
            "BluePyEModel axon strategy. The default tapered modifier creates a myelinated "
            "section list. Legacy and BluePyOpt replacement do not create one; no replacement "
            "leaves source myelination unknown. Select a different modifier to update the "
            "available section-list choices."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION,
            "choices": AXON_MODIFIER_DESCRIPTIONS,
        },
    )

    def to_pipeline_settings(self) -> dict[str, list[str]]:
        """Return the BluePyEModel pipeline setting for the selected modifier."""
        if self.axon_modifier == AxonModifier.NONE:
            return {"morph_modifiers": []}
        return {"morph_modifiers": [self.axon_modifier.value]}

    @property
    def expected_myelinated(self) -> bool | None:
        """Expected myelination produced by the selected strategy."""
        if self.axon_modifier in {
            AxonModifier.REPLACE_AXON_WITH_TAPER,
            AxonModifier.REPLACE_AXON_OLFACTORY_BULB,
        }:
            return True
        if self.axon_modifier in {
            AxonModifier.REPLACE_AXON_LEGACY,
            AxonModifier.BLUEPYOPT_REPLACE_AXON,
        }:
            return False
        return None

    def section_list_choices(self) -> tuple[SectionListChoice, ...]:
        """Return section-list choices for the selected morphology modifier."""
        return DEFAULT_SECTION_LIST_CATALOG.choices(axon_modifier=self.axon_modifier)

    def available_section_list_names(self) -> tuple[SectionListName, ...]:
        """Return section-list names currently selectable in the form."""
        return tuple(choice.name for choice in self.section_list_choices() if choice.available)


def _fixed_parameter(value: float) -> ParameterSelection:
    return ParameterSelection(value=OptimizationValue(value=value))


def _bounded_parameter(lower: float, upper: float) -> ParameterSelection:
    return ParameterSelection(
        value=OptimizationValue(mode="bounds", bounds=(lower, upper)),
    )


def _default_global_parameters() -> dict[str, GlobalParameterSelection]:
    return {
        "v_init": GlobalParameterSelection(value=OptimizationValue(value=-80.0)),
        "celsius": GlobalParameterSelection(value=OptimizationValue(value=34.0)),
    }


def _default_base_parameters() -> dict[SectionListName, dict[str, ParameterSelection]]:
    return {
        "all": {
            "Ra": _fixed_parameter(100.0),
            "g_pas": _bounded_parameter(1e-5, 6e-5),
            "e_pas": _bounded_parameter(-95.0, -60.0),
        },
        "myelinated": {"cm": _fixed_parameter(0.02)},
        "axonal": {
            "cm": _fixed_parameter(1.0),
            "ena": _fixed_parameter(50.0),
            "ek": _fixed_parameter(-90.0),
        },
        "somatic": {
            "cm": _fixed_parameter(1.0),
            "ena": _fixed_parameter(50.0),
            "ek": _fixed_parameter(-90.0),
        },
        "apical": {
            "cm": _fixed_parameter(2.0),
            "ena": _fixed_parameter(50.0),
            "ek": _fixed_parameter(-90.0),
        },
        "basal": {
            "cm": _fixed_parameter(2.0),
            "ena": _fixed_parameter(50.0),
            "ek": _fixed_parameter(-90.0),
        },
    }


class ParametersSelection(Block):
    """Mechanisms and values selected for the optimization params compiler.

    Rendered by the UI as the "Mechanisms" card, expanded into the 3-step wizard
    listed in ``MECHANISMS_WIZARD_STEPS``: Mechanism Selection, Region assignment,
    and Parameters selection. Distribution selection is a per-row choice (see
    ``ParameterSelection.distribution``) against the combined standard + custom
    catalog, not a separate wizard step.
    """

    steps: ClassVar[tuple[str, ...]] = MECHANISMS_WIZARD_STEPS

    ion_channel_models: tuple[IonChannelModelFromID, ...] = Field(
        default_factory=tuple,
        title="Ion channel models",
        description=(
            "Ion channel model entities whose .mod assets are staged into mechanisms. "
            "The same entity may be assigned to multiple regions."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER_MULTIPLE,
            SchemaKey.STEP: MECHANISM_SELECTION_STEP,
            SchemaKey.STEP_ORDER: 1,
        },
    )
    mechanism_regions: dict[SectionListName, tuple[MechanismRegionSelection, ...]] = Field(
        default_factory=dict,
        title="Mechanisms by region",
        description=(
            "Assign selected IonChannelModel entities and parameters to a canonical "
            "BluePyEModel section list. Composite choices expand through the recipe map. "
            "Overlapping rows are preserved and compiled from broad to narrow locations."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.SINGULAR_NAME: "Mechanism Region",
            "choices": DEFAULT_SECTION_LIST_CATALOG.schema_choices(),
            "availability_by_axon_modifier": (
                DEFAULT_SECTION_LIST_CATALOG.schema_availability_by_modifier()
            ),
            "alias_expansions": DEFAULT_SECTION_LIST_CATALOG.to_recipe_multiloc_map(),
            SchemaKey.STEP: REGION_ASSIGNMENT_STEP,
            SchemaKey.STEP_ORDER: 2,
        },
    )
    global_parameters: dict[str, GlobalParameterSelection] = Field(
        default_factory=_default_global_parameters,
        title="Global parameters",
        description=(
            "Editable global values such as v_init and celsius. Shown as the 'Global' card; "
            "see parameter_group_view for the Figma-shaped card list, which keeps distribution "
            "constants on their own 'Distribution parameters' card."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.SINGULAR_NAME: "Global Parameter",
            "derived_view": "parameter_group_view",
            SchemaKey.STEP: PARAMETERS_SELECTION_STEP,
            SchemaKey.STEP_ORDER: 4,
        },
    )
    base_parameters: dict[SectionListName, dict[str, ParameterSelection]] = Field(
        default_factory=_default_base_parameters,
        title="Base and passive parameters",
        description=(
            "Editable built-in parameters such as pas, cm, Ra, g_pas, and e_pas. "
            "Regional rows use the canonical section-list catalog and expose the distance "
            "distribution selector. Overlapping rows are preserved and compiled from broad "
            "to narrow locations."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.SINGULAR_NAME: "Base Parameter Region",
            "choices": DEFAULT_SECTION_LIST_CATALOG.schema_choices(),
            "availability_by_axon_modifier": (
                DEFAULT_SECTION_LIST_CATALOG.schema_availability_by_modifier()
            ),
            "alias_expansions": DEFAULT_SECTION_LIST_CATALOG.to_recipe_multiloc_map(),
            SchemaKey.STEP: PARAMETERS_SELECTION_STEP,
            SchemaKey.STEP_ORDER: 4,
        },
    )
    distribution_parameters: dict[str, dict[str, OptimizationValue]] = Field(
        default_factory=dict,
        title="Distribution parameters",
        description=(
            "Values for placeholders declared by reusable distance-dependent distributions."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.SINGULAR_NAME: "Distribution Parameter",
            SchemaKey.STEP: PARAMETERS_SELECTION_STEP,
            SchemaKey.STEP_ORDER: 4,
        },
    )

    def _global_group_rows(self) -> tuple[ParameterRowView, ...]:
        return tuple(
            ParameterRowView(
                group_key="global",
                kind="global",
                key=name,
                name=name,
                value=selection.value,
                location="global",
                ion_channel_model=selection.ion_channel_model,
            )
            for name, selection in sorted(self.global_parameters.items())
        )

    def _distribution_group_rows(self) -> tuple[ParameterRowView, ...]:
        return tuple(
            ParameterRowView(
                group_key="distribution",
                kind="distribution",
                key=f"distribution_{distribution_name}.{name}",
                name=name,
                value=value,
                location=f"distribution_{distribution_name}",
                distribution=distribution_name,
            )
            for distribution_name in sorted(self.distribution_parameters)
            for name, value in sorted(self.distribution_parameters[distribution_name].items())
        )

    def _region_group_rows(self, location: SectionListName) -> tuple[ParameterRowView, ...]:
        empty_base: dict[str, ParameterSelection] = {}
        base_parameters = self.base_parameters.get(location, empty_base)
        mechanism_assignments = self.mechanism_regions.get(location) or ()
        rows = [
            ParameterRowView(
                group_key=location,
                kind="region",
                key=f"{location}.{name}",
                name=name,
                value=selected.value,
                location=location,
                mechanism="pas" if name in {"g_pas", "e_pas"} else None,
                distribution=selected.distribution,
            )
            for name, selected in sorted(base_parameters.items())
        ]
        rows.extend(
            ParameterRowView(
                group_key=location,
                kind="region",
                key=f"{location}.{assignment.ion_channel_model.id_str}.{name}",
                name=name,
                value=selected.value,
                location=location,
                mechanism=assignment.ion_channel_model.id_str,
                distribution=selected.distribution,
                ion_channel_model=assignment.ion_channel_model,
            )
            for assignment in mechanism_assignments
            for name, selected in sorted(assignment.parameters.items())
        )
        return tuple(rows)

    def parameter_rows(self, group_key: str) -> tuple[ParameterRowView, ...]:
        """Return the editable rows for one parameter-group card."""
        if group_key == "global":
            return self._global_group_rows()
        if group_key == "distribution":
            return self._distribution_group_rows()
        return self._region_group_rows(group_key)  # ty:ignore[invalid-argument-type]

    @property
    def parameter_group_view(self) -> tuple[ParameterGroupView, ...]:
        """Figma-shaped card list: ``Global``, ``Distribution parameters``, then regions.

        Regions are ordered by the section-list catalog's display order and only
        included when they have configured base or mechanism parameters, so the
        card list matches what the user has actually configured.
        """
        groups = [
            ParameterGroupView(
                key="global",
                kind="global",
                label="Global",
                description="Global values such as v_init and celsius.",
                order=0,
                item_count=len(self.global_parameters),
                count_label=f"{len(self.global_parameters)} parameters",
            ),
            ParameterGroupView(
                key="distribution",
                kind="distribution",
                label="Distribution parameters",
                description="Values for placeholders declared by distance-dependent distributions.",
                order=1,
                item_count=sum(len(values) for values in self.distribution_parameters.values()),
                count_label=(
                    f"{sum(len(values) for values in self.distribution_parameters.values())} "
                    "parameters"
                ),
            ),
        ]
        configured_locations = set(self.base_parameters) | set(self.mechanism_regions)
        ordered_choices = sorted(
            (
                choice
                for choice in DEFAULT_SECTION_LIST_CATALOG.choices()
                if choice.name in configured_locations
            ),
            key=lambda choice: choice.display_order,
        )
        for order, choice in enumerate(ordered_choices, start=len(groups)):
            channels_assigned = len(self.mechanism_regions.get(choice.name, ()))
            groups.append(
                ParameterGroupView(
                    key=choice.name,
                    kind="region",
                    label=choice.label,
                    description=choice.description,
                    order=order,
                    item_count=channels_assigned,
                    count_label=f"{channels_assigned} channels assigned",
                    section_lists=DEFAULT_SECTION_LIST_CATALOG.expand(choice.name),
                )
            )
        return tuple(groups)

    @property
    def ion_channel_model_references(self) -> tuple[IonChannelModelFromID, ...]:
        """All referenced IonChannelModel entities, deduplicated by entity ID."""
        references = list(self.ion_channel_models)
        references.extend(
            assignment.ion_channel_model
            for selections in self.mechanism_regions.values()
            for assignment in selections
        )
        references.extend(
            selection.ion_channel_model
            for selection in self.global_parameters.values()
            if selection.ion_channel_model is not None
        )
        unique_references: dict[str, IonChannelModelFromID] = {}
        for reference in references:
            unique_references.setdefault(reference.id_str, reference)
        return tuple(unique_references.values())

    @model_validator(mode="after")
    def validate_selection_references(self) -> "ParametersSelection":
        """Validate locations and ensure regional references were selected."""
        selected_ids = {model.id_str for model in self.ion_channel_models}
        if len(selected_ids) != len(self.ion_channel_models):
            msg = "ion_channel_models must not contain duplicate entity IDs."
            raise ValueError(msg)
        for location, selections in self.mechanism_regions.items():
            if location not in REGIONAL_PARAMETER_LOCATIONS:
                msg = f"Unsupported mechanism region: {location}."
                raise ValueError(msg)
            for selection in selections:
                if selection.ion_channel_model.id_str not in selected_ids:
                    msg = "Every mechanism region entity must also be listed in ion_channel_models."
                    raise ValueError(msg)
        for name, selection in self.global_parameters.items():
            if (
                selection.ion_channel_model is not None
                and selection.ion_channel_model.id_str not in selected_ids
            ):
                msg = f"Global parameter '{name}' source must also be listed in ion_channel_models."
                raise ValueError(msg)
        for location in self.base_parameters:
            if location not in REGIONAL_PARAMETER_LOCATIONS:
                msg = f"Unsupported base parameter region: {location}."
                raise ValueError(msg)
        return self


Probability = Annotated[float, Field(ge=0.0, le=1.0)]
ProbabilityValue = Probability | list[Probability]


class EfelSettings(BaseModel):
    """Validated common eFEL settings forwarded through the pipeline recipe."""

    model_config = ConfigDict(extra="allow")

    strict_stiminterval: bool = True
    interp_step: PositiveFloat = 0.025


class PhasePlotSettings(BaseModel):
    """Settings for BluePyEModel phase-plot analysis."""

    model_config = ConfigDict(extra="forbid")

    prot_names: tuple[str, ...] = ("idrest",)
    amplitude: float = 150.0
    amp_window: PositiveFloat = 1.5
    relative_amp: bool = True

    def to_recipe_dict(self) -> dict[str, Any]:
        """Serialize tuple-based form metadata as the recipe list expected by BluePyEModel."""
        return {
            "prot_names": list(self.prot_names),
            "amplitude": self.amplitude,
            "amp_window": self.amp_window,
            "relative_amp": self.relative_amp,
        }


class SineSpecSettings(BaseModel):
    """Settings for optional BluePyEModel SineSpec analysis."""

    model_config = ConfigDict(extra="forbid")

    amp: PositiveFloat = 0.05
    threshold_based: bool = False


class OptimizationParams(Block):
    """Algorithm-specific ``optimisation_params`` passed to BluePyEModel."""

    offspring_size: PositiveInt | list[PositiveInt] = Field(
        default=20,
        le=200,
        title="Offspring size",
        description=(
            "Population size per generation. The L5PC example uses 20; we default"
            " to a small value so the bundled example completes quickly."
            " Allowed range: 1-200."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    sigma: PositiveFloat | list[PositiveFloat] | None = Field(
        default=None,
        title="CMA initial sigma",
        description=(
            "Initial standard deviation for SO-CMA or MO-CMA. Leave empty to use "
            "BluePyEModel's optimizer default."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    weight_hv: ProbabilityValue | None = Field(
        default=None,
        title="MO-CMA hypervolume weight",
        description=(
            "Weight of the hypervolume score for MO-CMA. Only valid for MO-CMA; "
            "leave empty to use the BluePyEModel default."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    eta: PositiveFloat | list[PositiveFloat] | None = Field(
        default=None,
        title="IBEA distribution index",
        description="Distribution index for IBEA crossover/mutation. Only valid for IBEA.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    mutpb: ProbabilityValue | None = Field(
        default=None,
        title="IBEA mutation probability",
        description="Mutation probability for IBEA; only valid for IBEA.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    cxpb: ProbabilityValue | None = Field(
        default=None,
        title="IBEA crossover probability",
        description="Crossover probability for IBEA; only valid for IBEA.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    centroids: tuple[float, ...] | None = Field(
        default=None,
        title="CMA centroids",
        description="Optional fixed initial CMA centroid vector; valid for SO-CMA and MO-CMA.",
    )

    @model_validator(mode="after")
    def validate_centroids(self) -> "OptimizationParams":
        """Reject non-finite initial centroid values."""
        if self.centroids is not None and any(not math.isfinite(value) for value in self.centroids):
            msg = "CMA centroids must contain only finite values."
            raise ValueError(msg)
        return self

    def validate_for_optimiser(self, optimiser: str) -> None:
        """Reject optimizer parameters that BluePyEModel will not consume."""
        cma_values = {
            "sigma": self.sigma,
            "weight_hv": self.weight_hv,
            "centroids": self.centroids,
        }
        ibea_values = {
            "eta": self.eta,
            "mutpb": self.mutpb,
            "cxpb": self.cxpb,
        }
        if optimiser == "IBEA" and any(value is not None for value in cma_values.values()):
            msg = "sigma, weight_hv, and centroids are only valid for SO-CMA or MO-CMA."
            raise ValueError(msg)
        if optimiser != "IBEA" and any(value is not None for value in ibea_values.values()):
            msg = "eta, mutpb, and cxpb are only valid for IBEA."
            raise ValueError(msg)
        if optimiser == "SO-CMA" and self.weight_hv is not None:
            msg = "weight_hv is only valid for MO-CMA."
            raise ValueError(msg)

    def to_dict(self, optimiser: str = "MO-CMA") -> dict[str, Any]:
        """Serialize only parameters accepted by the selected BluePyEModel optimizer."""
        self.validate_for_optimiser(optimiser)
        result: dict[str, Any] = {"offspring_size": self.offspring_size}
        if optimiser in {"SO-CMA", "MO-CMA"}:
            if self.sigma is not None:
                result["sigma"] = self.sigma
            if self.centroids is not None:
                result["centroids"] = list(self.centroids)
            if optimiser == "MO-CMA" and self.weight_hv is not None:
                result["weight_hv"] = self.weight_hv
        else:
            for name in ("eta", "mutpb", "cxpb"):
                value = getattr(self, name)
                if value is not None:
                    result[name] = value
        return result


class OptimizationSettings(Block):
    """Pydantic form for optimization, evaluation, validation, and analysis recipe settings."""

    optimiser: Literal["SO-CMA", "MO-CMA", "IBEA"] = Field(
        default="MO-CMA",
        title="Optimiser",
        description=(
            "BluePyEModel optimiser. ``SO-CMA`` is single-objective CMA, ``MO-CMA`` is "
            "multi-objective CMA, and ``IBEA`` is the Indicator-Based Evolutionary Algorithm."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    max_ngen: PositiveInt | list[PositiveInt] = Field(
        default=100,
        title="Max generations",
        description="Maximum number of optimizer generations.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    optimisation_timeout: PositiveFloat | list[PositiveFloat] = Field(
        default=300.0,
        title="Optimisation timeout",
        description="Maximum duration in seconds for an optimization evaluation.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    optimisation_checkpoint_period: NonNegativeFloat | list[NonNegativeFloat] | None = Field(
        default=None,
        title="Checkpoint period",
        description=(
            "Minimum seconds between optimization checkpoint writes; empty uses the "
            "backend default."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL},
    )
    use_stagnation_criterion: bool = Field(
        default=True,
        title="Use stagnation criterion",
        description="Enable optimizer stagnation stopping in addition to max generations.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    threshold_efeature_std: NonNegativeFloat | list[NonNegativeFloat] | None = Field(
        default=None,
        title="E-feature standard-deviation threshold",
        description=(
            "Optional minimum standard deviation relative to each e-feature mean "
            "during optimization."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL},
    )
    minimum_protocol_delay: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.0,
        title="Minimum protocol delay",
        description="Minimum initial protocol delay in seconds used by optimization evaluations.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    stochasticity: bool | tuple[str, ...] = Field(
        default=False,
        title="Stochasticity",
        description="Enable stochastic mechanisms globally or only for the listed protocol names.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    validation_function: Literal["max_score", "mean_score"] = Field(
        default="max_score",
        title="Validation function",
        description="Safe built-in validation score function used by downstream validation.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    validation_threshold: PositiveFloat | list[PositiveFloat] = Field(
        default=5.0,
        title="Validation threshold",
        description="Score threshold below which a model is considered validated.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    seed: NonNegativeInt | list[NonNegativeInt] = Field(
        default=1,
        title="Random seed",
        description=(
            "Seed forwarded to setup_and_run_optimisation. It is execution-only and is not "
            "written into recipes.json."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )

    neuron_dt: PositiveFloat | list[PositiveFloat] | None = Field(
        default=None,
        title="NEURON fixed time step",
        description="Simulation time step; empty selects BluePyEModel CVode behavior.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL},
    )
    cvode_minstep: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.0,
        title="CVode minimum step",
        description="Minimum time step permitted by CVode.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    use_params_for_seed: bool = Field(
        default=True,
        title="Seed simulator from parameters",
        description="Use a hash of the parameter dictionary as the simulator seed.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    current_precision: PositiveFloat | list[PositiveFloat] = Field(
        default=0.01,
        title="Current search precision",
        description="Current interval precision for threshold and rheobase searches.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    max_threshold_voltage: float | list[float] = Field(
        default=-30.0,
        title="Maximum threshold voltage",
        description="Upper voltage bound used during threshold and rheobase searches.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    strict_holding_bounds: bool = Field(
        default=True,
        title="Strict holding-current bounds",
        description="Keep the configured holding-current search bounds fixed.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    max_depth_holding_search: PositiveInt | list[PositiveInt] = Field(
        default=7,
        title="Holding search depth",
        description="Maximum binary-search depth for holding current.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    max_depth_threshold_search: PositiveInt | list[PositiveInt] = Field(
        default=10,
        title="Threshold search depth",
        description="Maximum binary-search depth for threshold current.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    spikecount_timeout: PositiveFloat | list[PositiveFloat] = Field(
        default=50.0,
        title="Spike-count timeout",
        description="Timeout in seconds for spike-count searches.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    default_std_value: PositiveFloat | list[PositiveFloat] = Field(
        default=0.01,
        title="Default std value",
        description="Replacement standard deviation for zero-variance extracted features.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    efel_settings: EfelSettings = Field(
        default_factory=EfelSettings,
        title="eFEL settings",
        description="Validated common eFEL settings forwarded to optimization evaluations.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE},
    )
    validation_protocols: tuple[str, ...] = Field(
        default_factory=tuple,
        title="Validation protocols",
        description="Protocol names held out from optimization and used only for validation.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    name_rin_protocol: str | None = Field(
        default=None,
        title="Rin protocol name",
        description="Protocol used to compute input resistance; empty disables Rin correction.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    name_rmp_protocol: str | None = Field(
        default=None,
        title="RMP protocol name",
        description="Protocol for resting membrane potential; empty disables RMP correction.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    plot_optimisation_progress: bool = Field(
        default=True,
        title="Plot optimization progress",
        description="Plot optimizer progress from checkpoints.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_parameter_evolution: bool = Field(
        default=True,
        title="Plot parameter evolution",
        description="Plot parameter evolution during optimization.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_distributions: bool = Field(
        default=True,
        title="Plot distributions",
        description="Plot optimized parameter distributions.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_scores: bool = Field(
        default=True,
        title="Plot scores",
        description="Plot optimization scores.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_traces: bool = Field(
        default=True,
        title="Plot traces",
        description="Plot simulated and target traces.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_thumbnail: bool = Field(
        default=True,
        title="Plot thumbnail",
        description="Plot a thumbnail trace for the resulting model.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_currentscape: bool = Field(
        default=True,
        title="Plot currentscape",
        description="Plot currentscapes for optimization recordings.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_dendritic_ISI_CV: bool = Field(  # ruff: ignore[mixed-case-variable-in-class-scope]
        default=True,
        title="Plot dendritic ISI CV",
        description="Plot dendritic inter-spike-interval coefficient of variation when available.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_dendritic_rheobase: bool = Field(
        default=True,
        title="Plot dendritic rheobase",
        description="Plot dendritic rheobase when available.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_bAP_EPSP: bool = Field(  # ruff: ignore[mixed-case-variable-in-class-scope]
        default=False,
        title="Plot bAP/EPSP",
        description="Run and plot back-propagating action-potential and EPSP protocols.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_IV_curves: bool = Field(  # ruff: ignore[mixed-case-variable-in-class-scope]
        default=False,
        title="Plot IV curves",
        description="Plot IV curves; requires extracted BluePyEfe pickle data.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_FI_curve_comparison: bool = Field(  # ruff: ignore[mixed-case-variable-in-class-scope]
        default=False,
        title="Plot FI curve comparison",
        description="Plot experimental versus simulated FI curves.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_traces_comparison: bool = Field(
        default=False,
        title="Plot trace comparison",
        description="Plot simulated traces over experimental traces.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    run_plot_custom_sinspec: bool = Field(
        default=False,
        title="Run SineSpec plot",
        description="Run and plot the optional SineSpec protocol.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    IV_curve_prot_name: str = Field(
        default="iv",
        min_length=1,
        title="IV curve protocol",
        description="Protocol name used by IV curve analysis.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    FI_curve_prot_name: str = Field(
        default="idrest",
        min_length=1,
        title="FI curve protocol",
        description="Protocol name used by FI curve comparison.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    plot_phase_plot: bool = Field(
        default=False,
        title="Plot phase plot",
        description="Plot the phase trajectory for the configured protocol.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    phase_plot_settings: PhasePlotSettings = Field(
        default_factory=PhasePlotSettings,
        title="Phase plot settings",
        description="Protocol and amplitude settings for phase-plot analysis.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE},
    )
    sinespec_settings: SineSpecSettings = Field(
        default_factory=SineSpecSettings,
        title="SineSpec settings",
        description="Amplitude settings for optional SineSpec analysis.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE},
    )
    custom_bluepyefe_cells_pklpath: str | None = Field(
        default=None,
        title="Custom BluePyEfe cells pickle",
        description="Optional path to a non-standard BluePyEfe cells.pkl file.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    custom_bluepyefe_protocols_pklpath: str | None = Field(
        default=None,
        title="Custom BluePyEfe protocols pickle",
        description="Optional path to a non-standard BluePyEfe protocols.pkl file.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    save_recordings: bool = Field(
        default=False,
        title="Save recordings",
        description="Save optimization response recordings under the task output directory.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    def to_dict(self, optimisation_params: OptimizationParams) -> dict[str, Any]:
        """Serialize validated fields using BluePyEModel's recipe setting names."""
        optimisation_params.validate_for_optimiser(self.optimiser)
        d: dict[str, Any] = {
            "optimiser": self.optimiser,
            "max_ngen": self.max_ngen,
            "optimisation_timeout": self.optimisation_timeout,
            "optimisation_params": optimisation_params.to_dict(self.optimiser),
            "validation_function": self.validation_function,
            "validation_threshold": self.validation_threshold,
            "default_std_value": self.default_std_value,
            "efel_settings": self.efel_settings.model_dump(mode="json"),
            "validation_protocols": list(self.validation_protocols),
            "optimisation_checkpoint_period": self.optimisation_checkpoint_period,
            "use_stagnation_criterion": self.use_stagnation_criterion,
            "threshold_efeature_std": self.threshold_efeature_std,
            "minimum_protocol_delay": self.minimum_protocol_delay,
            "stochasticity": (
                list(self.stochasticity)
                if isinstance(self.stochasticity, tuple)
                else self.stochasticity
            ),
            "neuron_dt": self.neuron_dt,
            "cvode_minstep": self.cvode_minstep,
            "use_params_for_seed": self.use_params_for_seed,
            "current_precision": self.current_precision,
            "max_threshold_voltage": self.max_threshold_voltage,
            "strict_holding_bounds": self.strict_holding_bounds,
            "max_depth_holding_search": self.max_depth_holding_search,
            "max_depth_threshold_search": self.max_depth_threshold_search,
            "spikecount_timeout": self.spikecount_timeout,
            "plot_optimisation_progress": self.plot_optimisation_progress,
            "plot_parameter_evolution": self.plot_parameter_evolution,
            "plot_distributions": self.plot_distributions,
            "plot_scores": self.plot_scores,
            "plot_traces": self.plot_traces,
            "plot_thumbnail": self.plot_thumbnail,
            "plot_currentscape": self.plot_currentscape,
            "plot_dendritic_ISI_CV": self.plot_dendritic_ISI_CV,
            "plot_dendritic_rheobase": self.plot_dendritic_rheobase,
            "plot_bAP_EPSP": self.plot_bAP_EPSP,
            "plot_IV_curves": self.plot_IV_curves,
            "plot_FI_curve_comparison": self.plot_FI_curve_comparison,
            "plot_traces_comparison": self.plot_traces_comparison,
            "run_plot_custom_sinspec": self.run_plot_custom_sinspec,
            "IV_curve_prot_name": self.IV_curve_prot_name,
            "FI_curve_prot_name": self.FI_curve_prot_name,
            "plot_phase_plot": self.plot_phase_plot,
            "phase_plot_settings": self.phase_plot_settings.to_recipe_dict(),
            "sinespec_settings": self.sinespec_settings.model_dump(mode="json"),
            "save_recordings": self.save_recordings,
        }
        if self.name_rin_protocol is not None:
            d["name_Rin_protocol"] = self.name_rin_protocol
        if self.name_rmp_protocol is not None:
            d["name_rmp_protocol"] = self.name_rmp_protocol
        if self.custom_bluepyefe_cells_pklpath is not None:
            d["custom_bluepyefe_cells_pklpath"] = self.custom_bluepyefe_cells_pklpath
        if self.custom_bluepyefe_protocols_pklpath is not None:
            d["custom_bluepyefe_protocols_pklpath"] = self.custom_bluepyefe_protocols_pklpath
        return d

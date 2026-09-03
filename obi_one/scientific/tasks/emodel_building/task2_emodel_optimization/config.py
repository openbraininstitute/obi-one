"""ScanConfig and SingleConfig for the 02_emodel_optimization stage."""

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, ClassVar, Literal

from entitysdk import Client
from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import Field, model_validator

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.library.info_scan_config.config import (
    BlockGroup as InfoBlockGroup,
    InfoScanConfig,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.artifacts import (
    TASK2_CONFIG_CONTRACT_VERSION,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.blocks import (
    CustomDistanceDependentDistribution,
    EModelOptimisationParameters,
    MorphologySettings,
    OptimizationInitialize,
    OptimizationInputs,
    OptimizationParams,
    OptimizationSettings,
    ParametersSelection,
    default_distance_dependent_distributions,
    resolve_distance_dependent_distribution,
)


class BlockGroup(StrEnum):
    """Block groups for the optimisation stage, matching the Figma left navigation.

    Figma renders ``SETUP`` (Info, Initialization), ``INPUTS`` (Extraction TaskResult,
    Morphology, Mechanisms), and ``SETTINGS`` (the single "Optimisation settings" tab,
    which also holds morphology/axon settings and optimisation parameters).
    """

    SETUP = "Setup"
    INPUTS = "Inputs"
    SETTINGS = "Settings"


def _used_distribution_names(selection: ParametersSelection) -> set[str]:
    used_distributions = {"uniform"}
    used_distributions.update(
        parameter.distribution
        for selections in selection.mechanism_regions.values()
        for assignment in selections
        for parameter in assignment.parameters.values()
    )
    used_distributions.update(
        parameter.distribution
        for parameters in selection.base_parameters.values()
        for parameter in parameters.values()
    )
    return used_distributions


def _validate_section_list_availability(
    morphology_settings: MorphologySettings,
    selection: ParametersSelection,
) -> None:
    """Reject section-list rows stale for the selected axon modifier."""
    choices = {choice.name: choice for choice in morphology_settings.section_list_choices()}
    for field_name, regions in (
        ("base_parameters", selection.base_parameters),
        ("mechanism_regions", selection.mechanism_regions),
    ):
        for location in regions:
            choice = choices[location]
            if choice.available:
                continue
            msg = (
                f"emodel_optimisation_parameters.{field_name}.{location}: section list "
                f"is unavailable for morphology_settings.axon_modifier="
                f"'{morphology_settings.axon_modifier.value}': {choice.disabled_reason}"
            )
            raise ValueError(msg)


def _validate_distribution_declarations(
    selection: ParametersSelection,
    custom_distributions: Mapping[str, CustomDistanceDependentDistribution],
) -> None:
    for distribution_name, configured_parameters in selection.distribution_parameters.items():
        distribution = resolve_distance_dependent_distribution(
            distribution_name,
            custom_distributions,
        )
        if distribution is None:
            msg = (
                f"Distribution parameters reference undeclared distribution '{distribution_name}'."
            )
            raise ValueError(msg)
        declared = set(distribution.parameters or [])
        unknown = set(configured_parameters) - declared
        if unknown:
            msg = (
                f"Distribution '{distribution_name}' has undeclared parameters: {sorted(unknown)}."
            )
            raise ValueError(msg)


def _validate_used_distributions(
    selection: ParametersSelection,
    custom_distributions: Mapping[str, CustomDistanceDependentDistribution],
) -> None:
    used_distributions = _used_distribution_names(selection)
    resolved = {
        name: resolve_distance_dependent_distribution(name, custom_distributions)
        for name in used_distributions
    }
    missing_distributions = {
        name for name, distribution in resolved.items() if distribution is None
    }
    if missing_distributions:
        msg = f"Parameters reference undeclared distributions: {sorted(missing_distributions)}."
        raise ValueError(msg)

    for distribution_name in sorted(used_distributions):
        distribution = resolved[distribution_name]
        if distribution is None:  # pragma: no cover - guarded above
            continue
        declared = set(distribution.parameters or [])
        if not declared:
            continue
        configured = selection.distribution_parameters.get(distribution_name, {})
        missing = declared - set(configured)
        if missing:
            msg = (
                f"Used distribution '{distribution_name}' is missing values for "
                f"parameters: {sorted(missing)}."
            )
            raise ValueError(msg)


class EModelOptimizationScanConfig(InfoScanConfig):
    """ScanConfig for the BluePyEModel optimisation step.

    Registered TaskConfigs from this class are normally executed by a remote
    launch-system worker: the worker stages entity assets, compiles this config
    into the versioned params/recipe artifacts, runs BluePyEModel/NEURON, and
    registers the draft result. See ``EModelOptimizationTask.execute()`` for the
    optional local diagnostic path.
    """

    single_coord_class_name: ClassVar[str] = "EModelOptimizationSingleConfig"
    name: ClassVar[str] = "EModel Optimization"
    description: ClassVar[str] = (
        "Run BluePyEModel parameter optimisation against extracted features,"
        " followed by analysis and draft emodel export."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        # InfoBlockGroup.SETUP_BLOCK_GROUP and BlockGroup.SETUP share the value "Setup" by
        # design, so `info` and `initialize` render under one Figma "Setup" section.
        SchemaKey.GROUP_ORDER: [
            InfoBlockGroup.SETUP_BLOCK_GROUP,
            BlockGroup.INPUTS,
            BlockGroup.SETTINGS,
        ],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = (
        TaskConfigType.emodel_optimization__campaign
    )
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.emodel_optimization__config_generation
    )

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_parameters_selection(cls, data: Any) -> Any:
        """Accept the old root field and normalize it to the new representation."""
        if not isinstance(data, dict):
            return data
        values = dict(data)
        legacy = values.pop("parameters_selection", None)
        if legacy is None:
            return values
        if "emodel_optimisation_parameters" in values:
            msg = "Use either emodel_optimisation_parameters or parameters_selection, not both."
            raise ValueError(msg)
        if not isinstance(legacy, ParametersSelection):
            legacy = ParametersSelection.model_validate(legacy)
        values["emodel_optimisation_parameters"] = (
            EModelOptimisationParameters.from_parameters_selection(legacy)
        )
        return values

    @property
    def parameters_selection(self) -> ParametersSelection:
        """Canonical selection used by existing runtime code."""
        return self.emodel_optimisation_parameters.to_parameters_selection()

    def input_entities(self, db_client: Client) -> list:
        entities: list = [
            self.inputs.target_efeatures.entity(db_client=db_client),
            self.inputs.morphology.entity(db_client=db_client),
        ]
        entities.extend(
            reference.entity(db_client=db_client)
            for reference in self.parameters_selection.ion_channel_model_references
        )
        return entities

    @model_validator(mode="after")
    def validate_params_source(self) -> "EModelOptimizationScanConfig":
        """Ensure ion channel models are provided for the dynamic params builder."""
        if len(self.parameters_selection.ion_channel_models) == 0:
            msg = (
                "ion_channel_models must be set: the dynamic builder needs ion"
                " channel models to build the params file."
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def validate_optimization_settings(self) -> "EModelOptimizationScanConfig":
        """Reject algorithm-specific optimizer fields for another algorithm."""
        self.optimization_params.validate_for_optimiser(self.optimization_settings.optimiser)
        return self

    @model_validator(mode="after")
    def validate_parameter_selection(self) -> "EModelOptimizationScanConfig":
        """Validate section-list and distribution references across sibling blocks."""
        _validate_section_list_availability(
            self.morphology_settings,
            self.parameters_selection,
        )
        _validate_distribution_declarations(
            self.parameters_selection,
            self.distance_dependent_distributions,
        )
        _validate_used_distributions(
            self.parameters_selection,
            self.distance_dependent_distributions,
        )
        return self

    contract_version: Literal["task2-config-v2"] = Field(
        default=TASK2_CONFIG_CONTRACT_VERSION,
        frozen=True,
        title="Task 2 configuration contract version",
        description="Compatibility version consumed by the launch-system optimization runner.",
        json_schema_extra={SchemaKey.UI_ENABLED: False},
    )

    # --- Setup ---

    initialize: OptimizationInitialize = Field(
        title="Initialize",
        description="E-model name and E-type entity used by the ``EModel_pipeline`` constructor.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: InfoBlockGroup.SETUP_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    # --- Inputs ---

    inputs: OptimizationInputs = Field(
        default_factory=OptimizationInputs,
        title="Inputs",
        description="Extraction result and morphology entity.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.INPUTS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    emodel_optimisation_parameters: EModelOptimisationParameters = Field(
        default_factory=EModelOptimisationParameters,
        title="Mechanisms",
        description=(
            "Select mechanisms, assign them to section lists, and configure optimization "
            "parameters. Distance-dependent distribution declarations remain a top-level "
            "sibling and are displayed as step 3 of the Mechanisms workflow."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.EMODEL_OPTIMISATION_PARAMETERS,
            SchemaKey.GROUP: BlockGroup.INPUTS,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    distance_dependent_distributions: dict[str, CustomDistanceDependentDistribution] = Field(
        default_factory=default_distance_dependent_distributions,
        title="Custom distance-dependent distributions",
        description=(
            "User-defined distance-dependent parameter transformations. The ten standard "
            "distributions (uniform, exp, step, ...) are always selectable by name on any "
            "parameter row without being declared here; this field only holds custom "
            "distributions declared by the user."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.GROUP: BlockGroup.INPUTS,
            SchemaKey.GROUP_ORDER: 3,
            SchemaKey.STEP: "Distribution",
            SchemaKey.STEP_ORDER: 3,
            "wizard": "emodel_optimisation_parameters",
            SchemaKey.SINGULAR_NAME: "Custom Distance-Dependent Distribution",
        },
    )

    # --- Settings ---

    morphology_settings: MorphologySettings = Field(
        default_factory=MorphologySettings,
        title="Morphology settings",
        description="Axon replacement and morphology section-list behavior.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETTINGS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    optimization_settings: OptimizationSettings = Field(
        default_factory=OptimizationSettings,
        title="Optimization settings",
        description=(
            "Top-level ``pipeline_settings`` keys controlling optimisation, analysis, and export."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETTINGS,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    optimization_params: OptimizationParams = Field(
        default_factory=OptimizationParams,
        title="Optimization params",
        description="``optimisation_params`` (offspring size).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETTINGS,
            SchemaKey.GROUP_ORDER: 2,
        },
    )

    @property
    def campaign_name(self) -> str:
        return self.info.campaign_name

    @property
    def campaign_description(self) -> str:
        return self.info.campaign_description


class EModelOptimizationSingleConfig(EModelOptimizationScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`EModelOptimizationScanConfig`."""

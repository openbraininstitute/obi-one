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
    DistanceDependentDistributionUnion,
    MorphologySettings,
    OptimizationInitialize,
    OptimizationParams,
    OptimizationSettings,
    ParametersSelection,
    default_distance_dependent_distributions,
)


class BlockGroup(StrEnum):
    """Block groups for the optimisation stage."""

    INPUT = "Input"
    MORPHOLOGY = "Morphology"
    PARAMETERS = "Parameters"
    OPTIMIZATION = "Optimization Settings"


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
                f"parameters_selection.{field_name}.{location}: section list '{location}' "
                f"is unavailable for morphology_settings.axon_modifier="
                f"'{morphology_settings.axon_modifier.value}': {choice.disabled_reason}"
            )
            raise ValueError(msg)


def _validate_distribution_declarations(
    selection: ParametersSelection,
    distributions: Mapping[str, Any],
) -> None:
    for distribution_name, configured_parameters in selection.distribution_parameters.items():
        distribution = distributions.get(distribution_name)
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
    distributions: Mapping[str, Any],
) -> None:
    used_distributions = _used_distribution_names(selection)
    missing_distributions = used_distributions - set(distributions)
    if missing_distributions:
        msg = f"Parameters reference undeclared distributions: {sorted(missing_distributions)}."
        raise ValueError(msg)

    for distribution_name in sorted(used_distributions):
        declared = set(distributions[distribution_name].parameters or [])
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

    Runs optimisation + analysis + export in a single task. Seeds the working
    directory from the extraction ``TaskResult`` assets, downloads morphology
    and ion channel model entities, merges optimisation settings into the
    recipe, and runs ``pipeline.optimise()`` followed by analysis and export.
    """

    single_coord_class_name: ClassVar[str] = "EModelOptimizationSingleConfig"
    name: ClassVar[str] = "EModel Optimization"
    description: ClassVar[str] = (
        "Run BluePyEModel parameter optimisation against extracted features,"
        " followed by analysis and draft emodel export."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            InfoBlockGroup.SETUP_BLOCK_GROUP,
            BlockGroup.INPUT,
            BlockGroup.MORPHOLOGY,
            BlockGroup.PARAMETERS,
            BlockGroup.OPTIMIZATION,
        ],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = (
        TaskConfigType.emodel_optimization__campaign
    )
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.emodel_optimization__config_generation
    )

    def input_entities(self, db_client: Client) -> list:
        entities: list = [
            self.initialize.target_efeatures.entity(db_client=db_client),
            self.initialize.morphology.entity(db_client=db_client),
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

    contract_version: Literal["task2-config-v1"] = Field(
        default=TASK2_CONFIG_CONTRACT_VERSION,
        frozen=True,
        title="Task 2 configuration contract version",
        description="Compatibility version consumed by the launch-system optimization runner.",
        json_schema_extra={SchemaKey.UI_ENABLED: False},
    )

    initialize: OptimizationInitialize = Field(
        title="Initialize",
        description="Entity-based inputs and ``EModel_pipeline`` constructor arguments.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.INPUT,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    morphology_settings: MorphologySettings = Field(
        default_factory=MorphologySettings,
        title="Morphology settings",
        description="Axon replacement and morphology section-list behavior.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.MORPHOLOGY,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    parameters_selection: ParametersSelection = Field(
        default_factory=ParametersSelection,
        title="Parameters",
        description="Ion channel models, region assignments, and parameter values.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.PARAMETERS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    distance_dependent_distributions: dict[str, DistanceDependentDistributionUnion] = Field(
        default_factory=default_distance_dependent_distributions,
        title="Distance-dependent distributions",
        description=(
            "Reusable distance-dependent parameter transformations. Parameter rows select "
            "these distributions by name."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.GROUP: BlockGroup.PARAMETERS,
            SchemaKey.GROUP_ORDER: 1,
            SchemaKey.SINGULAR_NAME: "Distance-Dependent Distribution",
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
            SchemaKey.GROUP: BlockGroup.OPTIMIZATION,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    optimization_params: OptimizationParams = Field(
        default_factory=OptimizationParams,
        title="Optimization params",
        description="``optimisation_params`` (offspring size).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.OPTIMIZATION,
            SchemaKey.GROUP_ORDER: 1,
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

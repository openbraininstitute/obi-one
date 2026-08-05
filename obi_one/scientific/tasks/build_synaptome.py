import logging
from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar, cast

from entitysdk import Client, models, types
from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import Discriminator, Field

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.db_sdk.registration import circuit as circuit_registration
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.build_synaptome import (
    BuildSynaptomeResult,
    build_synaptome_artifact,
)
from obi_one.scientific.library.entity_property_types import MappedPropertiesGroup
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig
from obi_one.scientific.unions_and_references.distributions import (
    AllDistributionsReference,
    AllDistributionsUnion,
)
from obi_one.scientific.unions_and_references.morphology_locations import (
    MorphologyLocationsReference,
    MorphologyLocationUnion,
)
from obi_one.scientific.unions_and_references.synaptic_models import (
    SynapticModelReference,
    SynapticModelUnion,
)

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Block groups for the ME-model Synapse Placement form."""

    INFO = "Info"
    ME_MODEL = "ME-model"
    SYNAPTIC_PHYSIOLOGY = "Synaptic physiology"
    SYNAPSE_GROUPS = "Synapse groups"


class SynapticModelPlacer(Block):
    """Places synapses with a given synaptic model on a single-cell morphology."""

    title: ClassVar[str] = "Synaptic Model Placer"

    synaptic_model: SynapticModelReference = Field(
        title="Synaptic model",
        description="Synaptic physiology model assigned to this incoming synapse group.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [SynapticModelReference.__name__],
        },
    )
    placement_strategy: MorphologyLocationsReference = Field(
        title="Placement strategy",
        description=(
            "Existing morphology-location block used to place this group's incoming synapses. "
            "The number of locations corresponds to the number of synapses."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [MorphologyLocationsReference.__name__],
        },
    )


SynapticModelPlacerUnion = Annotated[
    SynapticModelPlacer,
    Discriminator("type"),
]


class MEModelSynapticModelPlacementScanConfig(InfoScanConfig):
    """Form for placing synaptic models on a single ME-model."""

    single_coord_class_name: ClassVar[str] = "MEModelSynapticModelPlacementSingleConfig"
    name: ClassVar[str] = "ME-model Synapse Placement"
    description: ClassVar[str] = "Place synaptic models on a single ME-model."

    _campaign_task_config_type: ClassVar[TaskConfigType] = (
        TaskConfigType.circuit_single_build__campaign
    )
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.circuit_single_build__config_generation
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.INFO,
            BlockGroup.ME_MODEL,
            BlockGroup.SYNAPTIC_PHYSIOLOGY,
            BlockGroup.SYNAPSE_GROUPS,
        ],
        SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS: {
            SynapticModelReference.__name__: "Select a synaptic model",
            AllDistributionsReference.__name__: (
                "Default: Built-in distribution (see field description)"
            ),
            MorphologyLocationsReference.__name__: "Select a placement strategy",
        },
        SchemaKey.PROPERTY_ENDPOINTS: {
            MappedPropertiesGroup.CIRCUIT: "/mapped-circuit-properties/{circuit_id}",
            MappedPropertiesGroup.MORPHOLOGY: "/mapped-morphology-properties/{circuit_id}",
        },
    }

    class Initialize(Block):
        """Configuration for the single-cell ME-model that receives incoming synapses."""

        title: ClassVar[str] = "Postsynaptic ME-model Initialization"

        me_model: MEModelFromID = Field(
            title="Postsynaptic ME-model",
            description=(
                "Existing single-cell ME-model providing the morphology and "
                "electrophysiological properties of the postsynaptic neuron."
            ),
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER,
                SchemaKey.PARAMETER_ORDER_PRIORITY: 100,
            },
        )

    def input_entities(self, db_client: Client) -> list[models.Entity]:
        """Return the ME-model used to build the synaptome."""
        return [self.initialize.me_model.entity(db_client=db_client)]

    info: Info = Field(
        title="Info",
        description="Information about the synapse placement.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.INFO,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    initialize: Initialize = Field(
        title="Postsynaptic ME-model",
        description=(
            "Existing single-cell ME-model providing the morphology and "
            "electrophysiological properties of the postsynaptic neuron receiving "
            "the incoming synapses."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.ME_MODEL,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    synaptic_models: dict[str, SynapticModelUnion] = Field(
        default_factory=dict,
        title="Synaptic models",
        description="Synaptic physiology models available for incoming synapse groups.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [SynapticModelReference.__name__],
            SchemaKey.SINGULAR_NAME: "Synaptic Model",
            SchemaKey.GROUP: BlockGroup.SYNAPTIC_PHYSIOLOGY,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    distributions: dict[str, AllDistributionsUnion] = Field(
        default_factory=dict,
        title="Distributions",
        description="Distributions used by synaptic physiology models.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.SINGULAR_NAME: "Distribution",
            SchemaKey.GROUP: BlockGroup.SYNAPTIC_PHYSIOLOGY,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    morphology_locations: dict[str, MorphologyLocationUnion] = Field(
        default_factory=dict,
        title="Placement strategies",
        description="Reusable morphology-location strategies for incoming synapse groups.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [MorphologyLocationsReference.__name__],
            SchemaKey.SINGULAR_NAME: "Placement Strategy",
            SchemaKey.GROUP: BlockGroup.SYNAPSE_GROUPS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    synapse_groups: dict[str, SynapticModelPlacerUnion] = Field(
        default_factory=dict,
        min_length=1,
        title="Synapse groups",
        description="Incoming synapse groups to attach to the ME-model.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [],
            SchemaKey.SINGULAR_NAME: "Synaptic Model Placer",
            SchemaKey.GROUP: BlockGroup.SYNAPSE_GROUPS,
            SchemaKey.GROUP_ORDER: 1,
        },
    )


class MEModelSynapticModelPlacementSingleConfig(
    MEModelSynapticModelPlacementScanConfig, SingleConfigMixin
):
    """Single-coordinate ME-model synapse placement config."""

    _single_task_config_type: ClassVar[TaskConfigType] = TaskConfigType.circuit_single_build__config
    _single_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.circuit_single_build__execution
    )


def build_synaptome(
    config: MEModelSynapticModelPlacementSingleConfig,
    output_directory: Path,
    *,
    db_client: Client,
) -> BuildSynaptomeResult:
    """Build and validate a simulatable single-neuron SONATA synaptome."""
    return build_synaptome_artifact(config, output_directory, db_client=db_client)


class MEModelSynapticModelPlacementTask(Task):
    """Build and register a single-cell synaptome circuit."""

    config: MEModelSynapticModelPlacementSingleConfig

    def execute(
        self,
        *,
        db_client: Client,
        entity_cache: bool = False,
        execution_activity_id: str | None = None,
    ) -> str:
        """Generate the SONATA artifact and register it through Activity provenance."""
        _ = entity_cache
        execution_activity = self._get_execution_activity(
            db_client=db_client,
            execution_activity_id=execution_activity_id,
        )
        me_model = cast(
            "models.MEModel",
            self.config.initialize.me_model.entity(db_client=db_client),
        )
        subject = me_model.morphology.subject
        if subject is None:
            msg = f"ME-model '{me_model.id}' morphology has no subject for Circuit registration."
            raise ValueError(msg)
        result = build_synaptome_artifact(
            self.config,
            self.config.coordinate_output_root / "SONATA",
            db_client=db_client,
        )

        circuit = circuit_registration.register_circuit(
            client=db_client,
            circuit_path=result.circuit_config_path,
            name=self.config.info.campaign_name,
            description=self.config.info.campaign_description,
            build_category=types.CircuitBuildCategory.computational_model,
            brain_region=me_model.brain_region,
            subject=subject,
            target_simulator=types.TargetSimulator.NEURON,
            experiment_date=me_model.morphology.experiment_date,
            license=me_model.license or me_model.morphology.license,
            skip_validation=True,
        )
        if circuit is None:
            msg = "Build Synaptome circuit registration did not return a Circuit."
            raise RuntimeError(msg)

        self._update_execution_activity(
            db_client=db_client,
            execution_activity=execution_activity,
            generated=[str(circuit.id)],
        )
        L.info("Build Synaptome completed. Output Circuit ID: %s", circuit.id)
        return str(circuit.id)

"""Scan config for building organoid-style SONATA circuits with sonata-builder."""

import logging
from enum import StrEnum
from typing import Any, ClassVar, Literal

from entitysdk.client import Client
from entitysdk.models import Entity
from pydantic import Field, model_validator

from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference
from obi_one.core.exception import OBIONEError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Block groups for the circuit build form."""

    SETUP = "Setup"
    CIRCUIT_DESIGN = "Circuit Design"
    CONNECTIVITY = "Connectivity"
    REGISTRATION = "Registration"


class CircuitPopulation(Block):
    """A cell population: a fraction of the circuit's cells sharing one ME-model."""

    fraction: float = Field(
        gt=0,
        le=1,
        title="Fraction",
        description=(
            "Fraction of the total cells belonging to this population. "
            "Fractions must sum to 1.0 across all populations."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    cell_class: Literal["excitatory", "inhibitory", "modulatory"] = Field(
        title="Cell Class",
        description="Cell class of this population.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    memodel: MEModelFromID = Field(
        title="ME-Model",
        description="ME-model entity providing morphology, hoc template and ion channel "
        "mechanisms for this population.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_SELECTOR_SINGLE},
    )
    evidence_level: Literal["E0", "E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"] = Field(
        default="E1",
        title="Evidence Level",
        description="Confidence in this population prior (E0 = guess, E3+ = measured).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )


class PopulationReference(BlockReference):
    """A reference to a population in the populations dictionary."""

    allowed_block_types: ClassVar[Any] = CircuitPopulation

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": [CircuitPopulation.__name__],
    }


class ConnectivityRuleBlock(Block):
    """A connectivity rule between two populations."""

    source_population: PopulationReference = Field(
        title="Source Population",
        description="Presynaptic population.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [PopulationReference.__name__],
        },
    )
    target_population: PopulationReference = Field(
        title="Target Population",
        description="Postsynaptic population.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [PopulationReference.__name__],
        },
    )
    p_max: float = Field(
        gt=0,
        le=1,
        title="Maximum Connection Probability",
        description="Connection probability at zero distance.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    lambda_um: float = Field(
        gt=0,
        title="Length Scale (μm)",
        description="Exponential decay length of the connection probability.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    synapses_per_pair_mean: float = Field(
        default=2.0,
        gt=0,
        title="Synapses per Connected Pair",
        description="Mean of the zero-truncated Poisson distribution for the number of "
        "synapses per connected pair.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    synapse_model: Literal["ProbAMPANMDA_EMS", "ProbGABAAB_EMS"] = Field(
        title="Synapse Model",
        description="Tsodyks-Markram synapse mechanism. Excitatory connections typically use "
        "ProbAMPANMDA_EMS, inhibitory ProbGABAAB_EMS.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    conductance_mean_ns: float = Field(
        default=2.5,
        gt=0,
        title="Mean Conductance (nS)",
        description="Mean of the lognormal synaptic conductance distribution.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    conductance_std_ns: float = Field(
        default=0.7,
        gt=0,
        title="Conductance Std (nS)",
        description="Standard deviation of the lognormal conductance distribution.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    u_syn_min: float = Field(
        default=0.2,
        gt=0,
        le=1,
        title="Min Utilization (u_syn)",
        description="Lower bound of the uniform u_syn distribution.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    u_syn_max: float = Field(
        default=0.5,
        gt=0,
        le=1,
        title="Max Utilization (u_syn)",
        description="Upper bound of the uniform u_syn distribution.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    decay_time_mean_ms: float = Field(
        default=8.0,
        gt=0,
        title="Mean Decay Time (ms)",
        description="Mean of the clipped-normal synaptic decay time distribution.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    decay_time_std_ms: float = Field(
        default=1.5,
        gt=0,
        title="Decay Time Std (ms)",
        description="Standard deviation of the decay time distribution.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    delay_base_ms: float = Field(
        default=1.0,
        gt=0,
        title="Base Delay (ms)",
        description="Distance-independent part of the synaptic delay.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    delay_per_um_ms: float = Field(
        default=0.01,
        ge=0,
        title="Delay per μm (ms)",
        description="Distance-dependent part of the synaptic delay.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    depression_time_ms: float = Field(
        default=200.0,
        gt=0,
        title="Depression Time (ms)",
        description="Depression time constant (D) of the Tsodyks-Markram model.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    facilitation_time_ms: float = Field(
        default=50.0,
        gt=0,
        title="Facilitation Time (ms)",
        description="Facilitation time constant (F) of the Tsodyks-Markram model.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    target_sections: list[Literal["soma", "axon", "basal", "apical"]] = Field(
        default=["soma", "basal", "apical"],
        min_length=1,
        title="Target Sections",
        description="Morphology sections afferent synapses may be placed on.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.MORPHOLOGY_SECTION_TYPE_SELECTION,
        },
    )
    allow_autapses: bool = Field(
        default=False,
        title="Allow Autapses",
        description="Whether a neuron may form synapses onto itself.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    evidence_level: Literal["E0", "E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"] = Field(
        default="E0",
        title="Evidence Level",
        description="Confidence in this connectivity prior (E0 = guess, E3+ = measured).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )


class OrganoidCircuitBuildScanConfig(InfoScanConfig):
    """Build a simulatable SONATA circuit from a biological description of a culture."""

    single_coord_class_name: ClassVar[str] = "OrganoidCircuitBuildSingleConfig"
    name: ClassVar[str] = "Organoid Circuit Build"
    description: ClassVar[str] = (
        "Generates a simulatable SONATA circuit (cells placed in a tissue geometry, wired by "
        "distance-dependent rules, synapses placed on real morphologies) from a description "
        "of an organoid or micro-culture. The circuit is registered in entitycore and can be "
        "simulated with the existing circuit simulation tasks."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP,
            BlockGroup.CIRCUIT_DESIGN,
            BlockGroup.CONNECTIVITY,
            BlockGroup.REGISTRATION,
        ],
    }

    def input_entities(self, db_client: Client) -> list[Entity]:
        """Return the MEModel entities used by all populations."""
        seen: dict[str, Entity] = {}
        for population in self.populations.values():
            entity = population.memodel.entity(db_client=db_client)
            seen[str(entity.id)] = entity
        return list(seen.values())

    class Initialize(Block):
        """Build parameters."""

        total_cells: int = Field(
            default=50,
            gt=0,
            le=1_000_000,
            title="Total Cells",
            description="Total number of cells in the circuit.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
        )
        seed: int = Field(
            default=0,
            ge=0,
            title="Random Seed",
            description="Root random seed. Identical configs produce identical circuits.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
        )
        export_profile: Literal["neurodamus_biophysical_v1", "structural_only"] = Field(
            default="neurodamus_biophysical_v1",
            title="Export Profile",
            description="'neurodamus_biophysical_v1' produces a fully simulatable circuit "
            "(synapse placement + cell model components). 'structural_only' produces an "
            "analysis-only circuit.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
        )

    class Experiment(Block):
        """Biological metadata describing the culture the circuit models."""

        preparation: Literal[
            "organoid_3d", "planar_culture", "organoid_on_mea", "assembloid", "custom"
        ] = Field(
            default="organoid_3d",
            title="Preparation",
            description="Biological preparation type.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
        )
        days_in_vitro: int = Field(
            default=90,
            ge=0,
            title="Days in Vitro",
            description="Age of the culture being modelled.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
        )
        species: str = Field(
            default="human",
            title="Species",
            description="Species of the cells (e.g. 'human', 'mouse'). Must match the "
            "subject used for registration.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        cell_source: str = Field(
            default="ipsc",
            title="Cell Source",
            description="Cell source (e.g. 'ipsc', 'primary').",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )

    class Geometry(Block):
        """Tissue geometry in which cells are placed."""

        shape: Literal["sphere", "disc", "sphere_on_substrate"] = Field(
            default="sphere",
            title="Shape",
            description="'sphere' for free-floating organoids, 'disc' for planar cultures, "
            "'sphere_on_substrate' for organoids settled on a substrate/MEA.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
        )
        radius_um: float = Field(
            default=150.0,
            gt=0,
            title="Radius (μm)",
            description="Radius of the tissue geometry.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
        )
        thickness_um: float = Field(
            default=10.0,
            gt=0,
            title="Thickness (μm)",
            description="Z-extent of the disc geometry (ignored for sphere).",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
        )
        min_soma_distance_um: float = Field(
            default=18.0,
            gt=0,
            title="Minimum Soma Distance (μm)",
            description="Minimum distance between cell bodies (Poisson-disc placement).",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
        )
        orientation: Literal["radial_outward", "radial_inward", "random", "fixed"] = Field(
            default="radial_outward",
            title="Orientation",
            description="Soma orientation method. 'radial_outward' points apicals away from "
            "the centre, typical for organoids.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
        )

    class Registration(Block):
        """entitycore registration metadata for the generated circuit."""

        register_in_entitycore: bool = Field(
            default=True,
            title="Register Circuit",
            description="Register the generated circuit in entitycore. Disable for local "
            "testing without a database connection.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
        )
        subject_name: str = Field(
            title="Subject",
            description="Name of the Subject entity this circuit is associated with.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        brain_region_name: str = Field(
            title="Brain Region",
            description="Name of the brain region entity.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        brain_region_hierarchy_name: str = Field(
            title="Brain Region Hierarchy",
            description="Name of the brain region hierarchy containing the region.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        license_label: str | None = Field(
            default=None,
            title="License",
            description="Label of the license entity (optional).",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        contact_email: str | None = Field(
            default=None,
            title="Contact Email",
            description="Contact email recorded on the circuit entity (optional).",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        experiment_date: str | None = Field(
            default=None,
            title="Experiment Date",
            description="Date of the experiment the circuit models (ISO format, optional).",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the circuit build.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    experiment: Experiment = Field(
        default_factory=Experiment,
        title="Experiment",
        description="Biological metadata describing the modelled culture.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 2,
        },
    )
    geometry: Geometry = Field(
        default_factory=Geometry,
        title="Geometry",
        description="Tissue geometry and cell placement.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.CIRCUIT_DESIGN,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    populations: dict[str, CircuitPopulation] = Field(
        default_factory=dict,
        title="Populations",
        description="Cell populations (e.g. 'exc', 'inh'). The dictionary key is the "
        "population name used in the generated circuit's node sets.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [PopulationReference.__name__],
            SchemaKey.SINGULAR_NAME: "Population",
            SchemaKey.GROUP: BlockGroup.CIRCUIT_DESIGN,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    connectivity_rules: dict[str, ConnectivityRuleBlock] = Field(
        default_factory=dict,
        title="Connectivity Rules",
        description="Distance-dependent connectivity rules between populations. The "
        "dictionary key is the rule name (e.g. 'exc_to_exc').",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [],
            SchemaKey.SINGULAR_NAME: "Connectivity Rule",
            SchemaKey.GROUP: BlockGroup.CONNECTIVITY,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    registration: Registration = Field(
        title="Registration",
        description="entitycore registration metadata for the generated circuit.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.REGISTRATION,
            SchemaKey.GROUP_ORDER: 0,
        },
    )


class OrganoidCircuitBuildSingleConfig(OrganoidCircuitBuildScanConfig, SingleConfigMixin):
    """Single configuration for one circuit build."""

    @model_validator(mode="after")
    def _validate_populations_and_rules(self) -> "OrganoidCircuitBuildSingleConfig":
        """Check that populations are consistent and rules reference them."""
        if not self.populations:
            msg = "At least one population must be defined."
            raise OBIONEError(msg)

        fraction_sum = sum(p.fraction for p in self.populations.values())
        if abs(fraction_sum - 1.0) > _FRACTION_SUM_TOLERANCE:
            msg = f"Population fractions must sum to 1.0 (got {fraction_sum:.4f})."
            raise OBIONEError(msg)

        for rule_name, rule in self.connectivity_rules.items():
            for role, ref in (
                ("source", rule.source_population),
                ("target", rule.target_population),
            ):
                if ref.block_name not in self.populations:
                    msg = (
                        f"Connectivity rule '{rule_name}' {role} population "
                        f"'{ref.block_name}' is not a defined population "
                        f"({sorted(self.populations)})."
                    )
                    raise OBIONEError(msg)
            if rule.u_syn_min > rule.u_syn_max:
                msg = f"Connectivity rule '{rule_name}': u_syn_min must be <= u_syn_max."
                raise OBIONEError(msg)
        return self


_FRACTION_SUM_TOLERANCE = 1e-6

import logging
import warnings
from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar

from entitysdk import models, types
from entitysdk.client import Client
from pydantic import Discriminator, Field

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.db_sdk.registration import circuit as circuit_registration
from obi_one.scientific.blocks.point_neuron_populations.pathway import (
    PathwayConnectionProbability,
)
from obi_one.scientific.unions_and_references.pathway_connection_probabilities import (
    PATHWAY_CONNECTION_PROBABILITY_REFERENCE_TYPES,
)
from obi_one.scientific.unions_and_references.point_neuron_populations import (
    POINT_NEURON_POPULATION_REFERENCE_TYPES,
    PointNeuronPopulationUnion,
)

L = logging.getLogger(__name__)

try:
    from obi_one.scientific.library.pd14_sonata_network import SonataNetworkFromConfig
except ImportError:
    warnings.warn(
        "PD14 network functionalities not available (the 'microcircuit' package is not installed).",
        UserWarning,
        stacklevel=1,
    )


class BlockGroup(StrEnum):
    """Block groups for the PD14 network write scan-config UI."""

    SETUP = "Setup"
    POPULATIONS = "Populations"
    CONNECTIVITY = "Connectivity"


class PD14NetworkWriteScanConfig(ScanConfig):
    """ScanConfig for parameterizing a point-neuron network and writing it to SONATA files.

    The network follows the point-neuron microcircuit model of Potjans & Diesmann (2014)
    (``microcircuit.sonata_network.SonataNetwork``), but its populations and connectivity are
    defined explicitly:

    - ``point_neuron_populations`` holds one ``PointNeuronPopulation`` block per neuronal
      population (name, neuron count, synapse class, external indegree, spatial extent, ...).
      The number of populations is arbitrary.
    - ``pathway_connection_probabilities`` holds one ``PathwayConnectionProbability`` block
      per connected pathway, each referencing a source and a target population and giving the
      mean PSP amplitude and relative weight standard deviation of the pathway. Together they
      define the connection-probability matrix: a pathway without a block defaults to a
      probability of 0.0, and two blocks with the same (source, target) pair raise an error.

    The neurons and connections are written to SONATA files (one ``nodes_<population>.h5``
    file per node population, ``edges.h5``, ``circuit_config.json`` and ``node_sets.json``)
    in the output directory.

    A thalamic (virtual) input population can be added via the ``Initialize`` parameters: its
    size is ``num_th_neurons`` (0 disables it) and its per-population connection probabilities
    are the ``thalamic_connection_probability`` of each ``PointNeuronPopulation``.
    """

    name: ClassVar[str] = "PD14 Network Write"
    description: ClassVar[str] = (
        "Parameterizes a point-neuron cortical network (Potjans & Diesmann 2014 style) from an"
        " explicit list of neuronal populations and pathway connection probabilities, and writes"
        " its neurons and connections to SONATA files."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP,
            BlockGroup.POPULATIONS,
            BlockGroup.CONNECTIVITY,
        ],
        # A reference field is only shown in the editor when a default label exists for one of its
        # reference types (see isReferenceFieldVisible in core-web-app). Provide one so the pathway
        # source/target population selectors render; the label is the placeholder shown when unset.
        SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS: dict.fromkeys(
            POINT_NEURON_POPULATION_REFERENCE_TYPES, "Select a population"
        ),
    }

    info: Info = Field(
        title="Info",
        description="Name and description of the PD14 network write campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    class Initialize(Block):
        n_scaling: float | list[float] = Field(
            default=1.0,
            title="Neuron number scaling factor",
            description="Factor by which the number of neurons in each population is scaled.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
        )
        k_scaling: float | list[float] = Field(
            default=1.0,
            title="Indegree scaling factor",
            description="Factor by which the indegrees (number of synapses) are scaled. Weights"
            " and DC input are adjusted to compensate when this differs from 1.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
        )
        bg_rate: float | list[float] = Field(
            default=8.0,
            title="Background rate",
            description="Rate of the external background input per external connection (in"
            " spikes/s). Only used when 'k_scaling' != 1, where it determines the compensating"
            " DC current (I_e) added to the neurons; it has no effect on the output when"
            " 'k_scaling' == 1.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
        )
        psp_ext: float | list[float] = Field(
            default=0.15,
            title="External PSP mean",
            description="Mean amplitude of the postsynaptic potential (in mV) of the external"
            " (background) input.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
        )
        delay_exc_mean: float | list[float] = Field(
            default=1.5,
            title="Excitatory delay mean",
            description="Mean delay of excitatory connections (in ms).",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
        )
        delay_inh_mean: float | list[float] = Field(
            default=0.75,
            title="Inhibitory delay mean",
            description="Mean delay of inhibitory connections (in ms).",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
        )
        delay_rel_std: float | list[float] = Field(
            default=0.5,
            title="Relative delay standard deviation",
            description="Relative standard deviation of the connection delays.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
        )
        rng_seed: int | list[int] = Field(
            default=55,
            title="Random number generator seed",
            description="Seed of the random number generator used for all random draws (initial"
            " membrane potentials, positions, connectivity, weights and delays).",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
        )
        num_th_neurons: int | list[int] = Field(
            default=902,
            title="Number of thalamic neurons",
            description="Number of neurons in the thalamic (virtual) input population (default"
            " from the model's stimulus parameters). If 0, the thalamic input is disabled and no"
            " thalamus population is written. Thalamo-cortical connections are only created for"
            " populations whose 'thalamic_connection_probability' is non-zero.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
        )
        psp_th: float | list[float] = Field(
            default=0.15,
            title="Thalamic PSP mean",
            description="Mean amplitude of the thalamic postsynaptic potential (in mV).",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
        )
        weight_th_rel_std: float | list[float] = Field(
            default=0.1,
            title="Thalamic relative weight standard deviation",
            description="Relative standard deviation of the thalamic synaptic weights.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
        )
        delay_th_mean: float | list[float] = Field(
            default=1.5,
            title="Thalamic delay mean",
            description="Mean delay of the thalamic input (in ms).",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
        )
        delay_th_rel_std: float | list[float] = Field(
            default=0.5,
            title="Thalamic relative delay standard deviation",
            description="Relative standard deviation of the thalamic delay.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
        )
        c_m: float | list[float] = Field(
            default=250.0,
            title="Membrane capacitance",
            description="Membrane capacitance C_m (in pF) of all neurons. Together with 'tau_m'"
            " and 'tau_syn' it determines the conversion of PSPs (mV) to synaptic currents (pA),"
            " so it also affects the connection weights.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
        )
        tau_m: float | list[float] = Field(
            default=10.0,
            title="Membrane time constant",
            description="Membrane time constant tau_m (in ms) of all neurons. Also affects the"
            " connection weights (see 'c_m').",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
        )
        tau_syn: float | list[float] = Field(
            default=0.5,
            title="Synaptic time constant",
            description="Time constant (in ms) of the postsynaptic currents of all neurons, used"
            " for both excitatory and inhibitory synapses. Also affects the connection weights"
            " (see 'c_m').",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
        )
        population_name: str | list[str] = Field(
            default="microcircuit",
            title="Node population name",
            description="Name of the SONATA node population containing all neurons.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        background_name: str | list[str] = Field(
            default="background",
            title="Background population name prefix",
            description="Name prefix of the virtual node populations representing background"
            " input (one per neuronal population).",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        thalamus_name: str | list[str] = Field(
            default="thalamus",
            title="Thalamus population name",
            description="Name of the virtual node population representing the thalamus. Ignored"
            " (no thalamus written) when 'num_th_neurons' is 0.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        write_indices: bool | list[bool] = Field(
            default=True,
            title="Write edge indices",
            description="Whether to write the SONATA source-to-target and target-to-source edge"
            " indices.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
        )

    initialize: Initialize = Field(
        title="Initialization",
        description="Global parameters of the network build.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    point_neuron_populations: dict[str, PointNeuronPopulationUnion] = Field(
        default_factory=dict,
        title="Point neuron populations",
        description="Neuronal populations of the network, keyed by block name.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: POINT_NEURON_POPULATION_REFERENCE_TYPES,
            SchemaKey.SINGULAR_NAME: "Point Neuron Population",
            SchemaKey.GROUP: BlockGroup.POPULATIONS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    pathway_connection_probabilities: dict[
        str, Annotated[PathwayConnectionProbability, Discriminator("type")]
    ] = Field(
        default_factory=dict,
        title="Pathway connection probabilities",
        description="Connection probabilities between populations, keyed by block name. Pathways"
        " without an entry default to a probability of 0.0.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: PATHWAY_CONNECTION_PROBABILITY_REFERENCE_TYPES,
            SchemaKey.SINGULAR_NAME: "Pathway Connection Probability",
            SchemaKey.GROUP: BlockGroup.CONNECTIVITY,
            SchemaKey.GROUP_ORDER: 0,
        },
    )


class PD14NetworkWriteSingleConfig(PD14NetworkWriteScanConfig, SingleConfigMixin):
    """Parameterizes a point-neuron network and writes it to SONATA files in the output dir."""


class PD14NetworkWriteTask(Task):
    config: PD14NetworkWriteSingleConfig

    # SONATA circuit configuration written at the root of the output directory.
    OUTPUT_CONFIG: ClassVar[str] = "circuit_config.json"

    def _register_output(self, db_client: Client, circuit_path: Path) -> models.Circuit | None:
        # Find static entities
        isocortex = db_client.search_entity(
            entity_type=models.BrainRegion,
            query={"name__ilike": "Isocortex"},
        ).first()
        mouse = db_client.search_entity(
            entity_type=models.Subject,
            query={"name": "Generic Mus musculus"},
        ).first()
        if isocortex is None:
            msg = "Could not find the 'Isocortex' brain region in entitycore."
            raise OBIONEError(msg)
        if mouse is None:
            msg = "Could not find the 'Generic Mus musculus' subject in entitycore."
            raise OBIONEError(msg)

        # Build circuit name and description
        campaign_str = self.config.info.campaign_name.replace(" ", "-")
        circuit_name = f"PD14_{campaign_str}"  # ty:ignore[unresolved-attribute]
        params = self.config.single_coordinate_scan_params.scan_params
        instance_info = ", ".join(f"{p.location_str}={p.value}" for p in params)
        if len(params) > 0:
            circuit_name = f"{circuit_name}-{self.config.idx}"
            instance_info = f" - Instance {self.config.idx} with {instance_info}"
        circuit_descr = self.config.info.campaign_description + instance_info

        return circuit_registration.register_circuit(
            client=db_client,
            circuit_path=circuit_path,
            name=circuit_name,
            description=circuit_descr,
            build_category=types.CircuitBuildCategory.computational_model,
            brain_region=isocortex,  # ty:ignore[unresolved-attribute, invalid-argument-type]
            subject=mouse,  # ty:ignore[unresolved-attribute, invalid-argument-type]
            target_simulator=types.TargetSimulator.NEST,
            experiment_date=None,
            license=None,  # TODO: Specify
            atlas=None,  # TODO: Not yet implemented
            root=None,
            parent=None,
            # TODO: Add a fitting derivation type to entitycore
            derivation_type=types.DerivationType.unspecified,
            skip_validation=True,
        )

    def execute(
        self,
        *,
        db_client: Client | None = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
        execution_activity_id: str | None = None,
    ) -> None:
        init = self.config.initialize
        execution_activity = PD14NetworkWriteTask._get_execution_activity(
            db_client=db_client, execution_activity_id=execution_activity_id
        )

        output_root = Path(self.config.coordinate_output_root)
        output_config = output_root / self.OUTPUT_CONFIG
        if output_config.exists():
            msg = f"Output file '{output_config}' already exists!"
            raise ValueError(msg)

        L.info(f"Info: Running idx {self.config.idx}")

        L.info(
            f"Writing PD14 SONATA network to '{output_root}' "
            f"({len(self.config.point_neuron_populations)} populations, "
            f"N_scaling={init.n_scaling}, K_scaling={init.k_scaling}, rng_seed={init.rng_seed})"
        )

        try:
            network = SonataNetworkFromConfig(self.config.model_dump(), str(output_root))
            network.create()
            network.connect()
            network.store_metadata()
        except NameError as e:
            # SonataNetworkFromConfig could not be imported (see module-level warning).
            msg = (
                "The PD14 network exporter (microcircuit.SonataNetworkFromConfig) is not available."
                " Install the 'microcircuit' package to use PD14NetworkWriteTask."
            )
            raise OBIONEError(msg) from e
        except OBIONEError:
            raise
        except ValueError as e:
            # Invalid configuration (e.g. duplicate pathway, unknown population reference).
            raise OBIONEError(str(e)) from e
        except Exception as e:
            message = f"Internal Server Error: {e}"
            raise OBIONEError(message) from e

        if not output_config.exists():
            msg = "PD14 SONATA network could not be written!"
            raise OBIONEError(msg)
        L.info(f"PD14 SONATA network successfully written to '{output_root}'")

        if db_client:
            new_circuit_entity = self._register_output(
                db_client=db_client, circuit_path=output_config
            )

            # Update execution activity (if any)
            if new_circuit_entity is not None:
                PD14NetworkWriteTask._update_execution_activity(
                    db_client=db_client,
                    execution_activity=execution_activity,
                    generated=[str(new_circuit_entity.id)],
                )

            L.info("Registration DONE")

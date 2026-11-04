import copy
import logging
import warnings
from pathlib import Path
from typing import Annotated, ClassVar

from entitysdk.client import Client
from entitysdk import models
import numpy as np
from pydantic import Discriminator, Field

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.scan_config import ScanConfig
from obi_one.core.info import Info
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.db_sdk.registration import circuit as circuit_registration
from obi_one.scientific.blocks.point_neuron_populations.pathway import (
    PathwayConnectionProbability,
)
from obi_one.scientific.blocks.point_neuron_populations.population import PointNeuronPopulation
from obi_one.scientific.unions_and_references.pathway_connection_probabilities import (
    PATHWAY_CONNECTION_PROBABILITY_REFERENCE_TYPES,
)
from obi_one.scientific.unions_and_references.point_neuron_populations import (
    POINT_NEURON_POPULATION_REFERENCE_TYPES,
)

L = logging.getLogger(__name__)

try:
    from microcircuit.sonata_network import SonataNetwork
    from microcircuit.stimulus_params import default_stim_dict
except ImportError:
    warnings.warn(
        "PD14 network functionalities not available (the 'microcircuit' package is not"
        " installed).",
        UserWarning,
        stacklevel=1,
    )


class PD14NetworkWriteScanConfig(ScanConfig):
    """ScanConfig for parameterizing a point-neuron network and writing it to SONATA files.

    The network follows the point-neuron microcircuit model of Potjans & Diesmann (2014)
    (``microcircuit.sonata_network.SonataNetwork``), but its populations and connectivity are
    defined explicitly:

    - ``point_neuron_populations`` holds one ``PointNeuronPopulation`` block per neuronal
      population (name, neuron count, synapse class, external indegree, spatial extent, ...).
      The number of populations is arbitrary.
    - ``pathway_connection_probabilities`` holds one ``PathwayConnectionProbability`` block
      per connected pathway, each referencing a source and a target population. Together they
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

    info: Info = Field(
        title="Info",
        description="Information about the circuit extraction campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: "Setup",
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    class Initialize(Block):
        n_scaling: float | list[float] = Field(
            default=1.0,
            title="Neuron number scaling factor",
            description="Factor by which the number of neurons in each population is scaled.",
        )
        k_scaling: float | list[float] = Field(
            default=1.0,
            title="Indegree scaling factor",
            description="Factor by which the indegrees (number of synapses) are scaled. Weights"
            " and DC input are adjusted to compensate when this differs from 1.",
        )
        bg_rate: float | list[float] = Field(
            default=8.0,
            title="Background rate",
            description="Rate of the external background input per external connection (in"
            " spikes/s). Only used when 'k_scaling' != 1, where it determines the compensating"
            " DC current (I_e) added to the neurons; it has no effect on the output when"
            " 'k_scaling' == 1.",
        )
        psp_exc_mean: float | list[float] = Field(
            default=0.15,
            title="Excitatory PSP mean",
            description="Mean amplitude of the excitatory postsynaptic potential (in mV).",
        )
        g: float | list[float] = Field(
            default=-4.0,
            title="Relative inhibitory weight",
            description="Relative inhibitory weight: the inhibitory PSP is 'g' times the"
            " excitatory PSP.",
        )
        weight_rel_std: float | list[float] = Field(
            default=0.1,
            title="Relative weight standard deviation",
            description="Relative standard deviation of the synaptic weights.",
        )
        delay_exc_mean: float | list[float] = Field(
            default=1.5,
            title="Excitatory delay mean",
            description="Mean delay of excitatory connections (in ms).",
        )
        delay_inh_mean: float | list[float] = Field(
            default=0.75,
            title="Inhibitory delay mean",
            description="Mean delay of inhibitory connections (in ms).",
        )
        delay_rel_std: float | list[float] = Field(
            default=0.5,
            title="Relative delay standard deviation",
            description="Relative standard deviation of the connection delays.",
        )
        rng_seed: int | list[int] = Field(
            default=55,
            title="Random number generator seed",
            description="Seed of the random number generator used for all random draws (initial"
            " membrane potentials, positions, connectivity, weights and delays).",
        )
        num_th_neurons: int | list[int] = Field(
            default=0,
            title="Number of thalamic neurons",
            description="Number of neurons in the thalamic (virtual) input population. If 0, the"
            " thalamic input is disabled and no thalamus population is written.",
        )
        psp_th: float | list[float] = Field(
            default=0.15,
            title="Thalamic PSP mean",
            description="Mean amplitude of the thalamic postsynaptic potential (in mV).",
        )
        delay_th_mean: float | list[float] = Field(
            default=1.5,
            title="Thalamic delay mean",
            description="Mean delay of the thalamic input (in ms).",
        )
        delay_th_rel_std: float | list[float] = Field(
            default=0.5,
            title="Thalamic relative delay standard deviation",
            description="Relative standard deviation of the thalamic delay.",
        )
        population_name: str | list[str] = Field(
            default="microcircuit",
            title="Node population name",
            description="Name of the SONATA node population containing all neurons.",
        )
        background_name: str | list[str | None] | None = Field(
            default="background",
            title="Background population name prefix",
            description="Name prefix of the virtual node populations representing background input"
            " (one per neuronal population), or null to omit them.",
        )
        thalamus_name: str | list[str | None] | None = Field(
            default="thalamus",
            title="Thalamus population name",
            description="Name of the virtual node population representing the thalamus, or null to"
            " omit it. Automatically treated as omitted when 'num_th_neurons' is 0.",
        )
        write_indices: bool | list[bool] = Field(
            default=True,
            title="Write edge indices",
            description="Whether to write the SONATA source-to-target and target-to-source edge"
            " indices.",
        )

    initialize: Initialize

    point_neuron_populations: dict[
        str, Annotated[PointNeuronPopulation, Discriminator("type")]
    ] = Field(
        default_factory=dict,
        title="Point neuron populations",
        description="Neuronal populations of the network, keyed by block name.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: POINT_NEURON_POPULATION_REFERENCE_TYPES,
            SchemaKey.SINGULAR_NAME: "Point Neuron Population",
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
        },
    )


class PD14NetworkWriteSingleConfig(PD14NetworkWriteScanConfig, SingleConfigMixin):
    """Parameterizes a point-neuron network and writes it to SONATA files in the output dir."""

    def ordered_populations(self) -> list[PointNeuronPopulation]:
        """Populations in a deterministic order (sorted by block name)."""
        return [
            self.point_neuron_populations[name] for name in sorted(self.point_neuron_populations)
        ]

    def population_index_by_name(self) -> dict[str, int]:
        """Map each population's block name to its index in ``ordered_populations()``."""
        return {name: i for i, name in enumerate(sorted(self.point_neuron_populations))}

    def connection_probability_matrix(self) -> "np.ndarray":
        """Assemble the connection-probability matrix from the pathway blocks.

        ``conn_probs[i][j]`` is the probability that a neuron of population ``j`` (source)
        connects to a neuron of population ``i`` (target), matching the ``SonataNetwork``
        convention. Missing pathways default to 0.0; a duplicate (source, target) pair raises.
        """
        index_by_name = self.population_index_by_name()
        num_pops = len(index_by_name)
        conn_probs = np.zeros((num_pops, num_pops))
        seen: set[tuple[int, int]] = set()
        for pathway in self.pathway_connection_probabilities.values():
            source_name = pathway.source.block.block_name
            target_name = pathway.target.block.block_name
            if source_name not in index_by_name:
                msg = (
                    f"Pathway source population '{source_name}' is not in"
                    " point_neuron_populations."
                )
                raise OBIONEError(msg)
            if target_name not in index_by_name:
                msg = (
                    f"Pathway target population '{target_name}' is not in"
                    " point_neuron_populations."
                )
                raise OBIONEError(msg)
            j = index_by_name[source_name]
            i = index_by_name[target_name]
            if (i, j) in seen:
                msg = (
                    f"Duplicate pathway connection probability for source '{source_name}' and"
                    f" target '{target_name}'."
                )
                raise OBIONEError(msg)
            seen.add((i, j))
            conn_probs[i][j] = pathway.connection_probability
        return conn_probs


class PD14NetworkWriteTask(Task):
    config: PD14NetworkWriteSingleConfig

    # SONATA circuit configuration written at the root of the output directory.
    OUTPUT_CONFIG: ClassVar[str] = "circuit_config.json"

    def _build_net_dict(self) -> dict:
        """Assemble the microcircuit ``net_dict`` from the config's blocks."""
        init = self.config.initialize
        populations = self.config.ordered_populations()
        if len(populations) == 0:
            msg = "At least one point neuron population must be defined."
            raise OBIONEError(msg)

        names = [p.population_name for p in populations]
        if len(set(names)) != len(names):
            msg = "Point neuron population names must be unique."
            raise OBIONEError(msg)

        num_pops = len(populations)
        synapse_classes = [str(p.synapse_class.value) for p in populations]

        # Excitatory/inhibitory PSP and delay matrices, built per source population from its
        # synapse class (column j), rather than from index parity as in the default model.
        exc_mean = init.psp_exc_mean
        inh_mean = init.psp_exc_mean * init.g
        psp_matrix = np.zeros((num_pops, num_pops))
        delay_matrix = np.zeros((num_pops, num_pops))
        for j, pop in enumerate(populations):
            is_exc = str(pop.synapse_class.value) == "EXC"
            psp_matrix[:, j] = exc_mean if is_exc else inh_mean
            delay_matrix[:, j] = init.delay_exc_mean if is_exc else init.delay_inh_mean

        net_dict = {
            "N_scaling": init.n_scaling,
            "K_scaling": init.k_scaling,
            "neuron_model": "iaf_psc_exp",
            "populations": names,
            "full_num_neurons": np.array([p.num_neurons for p in populations]),
            "full_mean_rates": np.array([p.mean_rate for p in populations]),
            "conn_probs": self.config.connection_probability_matrix(),
            "PSP_exc_mean": init.psp_exc_mean,
            "weight_rel_std": init.weight_rel_std,
            "g": init.g,
            "delay_exc_mean": init.delay_exc_mean,
            "delay_inh_mean": init.delay_inh_mean,
            "delay_rel_std": init.delay_rel_std,
            "bg_input_type": "poisson",
            "K_ext": np.array([p.k_ext for p in populations]),
            "bg_rate": init.bg_rate,
            "delay_poisson": init.delay_exc_mean,
            "V0_type": "optimized",
            "synapse_classes": synapse_classes,
            "layer_geometry": {
                p.population_name: {
                    "x": list(p.x_extent),
                    "y": list(p.y_extent),
                    "z": list(p.z_extent),
                }
                for p in populations
            },
            "neuron_params": {
                "V0_mean": {
                    "original": -58.0,
                    "optimized": [p.v0_mean for p in populations],
                },
                "V0_std": {
                    "original": 10.0,
                    "optimized": [p.v0_std for p in populations],
                },
                "E_L": -65.0,
                "V_th": -50.0,
                "V_reset": -65.0,
                "C_m": 250.0,
                "tau_m": 10.0,
                "tau_syn": 0.5,
                "t_ref": 2.0,
            },
            "PSP_matrix_mean": psp_matrix,
            "delay_matrix_mean": delay_matrix,
        }
        return net_dict

    def _register_output(self, db_client: Client, circuit_path: Path) -> models.Circuit | None:
        # Find static entities
        db_client.search_entity(
            entity_type=models.BrainRegion,
            query={"name": ""}
        )
        isocortex = db_client.search_entity(
            entity_type=models.BrainRegion,
            query={"name__ilike": "Isocortex"}
        ).first()
        mouse = db_client.search_entity(
            entity_type=models.Subject,
            query={"name": "Generic Mus musculus"}
        ).first()
        assert isocortex is not None
        assert mouse is not None
        # Build circuit name and description
        campaign_str = self.config.info.campaign_name.replace(" ", "-")
        circuit_name = f"PD14_{campaign_str}"  # ty:ignore[unresolved-attribute]
        params = self.config.single_coordinate_scan_params.scan_params
        instance_info = [
            f"{p.location_str}={p.value}"
            for p in params
        ]
        instance_info = ", ".join(instance_info)
        if len(params) > 0:
            circuit_name = f"{circuit_name}-{self.config.idx}"
            instance_info = f" - Instance {self.config.idx} with {instance_info}"
        circuit_descr = self.config.info.campaign_description + instance_info

        from entitysdk import types 
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
            derivation_type=types.DerivationType.unspecified,  # TODO: Add fitting type to entitycore
            skip_validation=True
        )

    def execute(
        self,
        *,
        db_client: Client | None = None,  # ruff: ignore[unused-method-argument]  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
        execution_activity_id: str | None = None,  # ruff: ignore[unused-method-argument]
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

        try:
            net_dict = self._build_net_dict()
        except OBIONEError:
            raise
        except Exception as e:
            message = f"Internal Server Error: {e}"
            raise OBIONEError(message) from e

        L.info(
            f"Writing PD14 SONATA network to '{output_root}' "
            f"({len(net_dict['populations'])} populations, N_scaling={init.n_scaling}, "
            f"K_scaling={init.k_scaling}, rng_seed={init.rng_seed})"
        )

        # Thalamic input. The per-population thalamo-cortical connection probabilities come from
        # the populations; the thalamic weight and delay from initialize. The thalamic input
        # timing and rate (th_start, th_duration, th_rate) do not affect the SONATA output (the
        # thalamus is a virtual population with no activity), so the model defaults are kept.
        # Setting num_th_neurons to 0 disables the thalamic input and omits the thalamus.
        thalamic_enabled = int(init.num_th_neurons) > 0
        thalamus_name = init.thalamus_name if thalamic_enabled else None

        conn_probs_th = np.array(
            [p.thalamic_connection_probability for p in self.config.ordered_populations()]
        )
        stim_dict = copy.deepcopy(default_stim_dict)
        stim_dict["thalamic_input"] = thalamic_enabled
        stim_dict["num_th_neurons"] = int(init.num_th_neurons)
        stim_dict["conn_probs_th"] = conn_probs_th
        stim_dict["PSP_th"] = init.psp_th
        stim_dict["delay_th_mean"] = init.delay_th_mean
        stim_dict["delay_th_rel_std"] = init.delay_th_rel_std

        sonata_dict = {
            "population_name": init.population_name,
            "background_name": init.background_name,
            "thalamus_name": thalamus_name,
            "write_indices": init.write_indices,
        }

        try:
            network = SonataNetwork(
                net_dict,
                str(output_root),
                stim_dict=stim_dict,
                sonata_dict=sonata_dict,
                rng_seed=init.rng_seed,
            )
            network.create()
            network.connect()
            network.store_metadata()
        except NameError as e:
            # SonataNetwork could not be imported (see module-level warning).
            msg = (
                "The PD14 network exporter (microcircuit.SonataNetwork) is not available."
                " Install the 'microcircuit' package to use PD14NetworkWriteTask."
            )
            raise OBIONEError(msg) from e
        except OBIONEError:
            raise
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


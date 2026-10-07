import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

import libsonata
from entitysdk import Client, models
from entitysdk.staging.circuit import stage_circuit as stage_circuit_entity
from entitysdk.staging.ion_channel_model import stage_sonata_from_config
from entitysdk.staging.memodel import stage_sonata_from_memodel

from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one_lazy.types import SimulationBackend
from obi_one.utils.circuit import count_cells_in_simulation_node_set
from obi_one.utils.io import load_json
from obi_one_lazy.scientific.library.circuit import Circuit
from obi_one_lazy.scientific.library.memodel_circuit import MEModelCircuit
from obi_one_lazy.scientific.library.simulation.neuron.schemas import (
    BluecellulabSimulationParameters,
    MechanismBuild,
    NeurodamusMechanismBuild,
    NeurodamusSimulationParameters,
    NeuronMechanismBuild,
    SimulationParameters,
)

if TYPE_CHECKING:
    from entitysdk.models import MEModel

L = logging.getLogger(__name__)


def stage_circuit(
    *, client: Client, model: models.Circuit, output_dir: Path, max_concurrent: int = 1
) -> Circuit:
    """Stage circuit."""
    circuit_config_path: Path = stage_circuit_entity(
        client=client,
        model=model,
        output_dir=output_dir,
        max_concurrent=max_concurrent,
    )
    return Circuit(name=cast("str", model.name), path=str(circuit_config_path))


def stage_ion_channel_models_as_circuit(
    *, client: Client, ion_channel_models: dict, output_dir: Path
) -> MEModelCircuit:
    # build ion channel model data dict for staging sonata config
    ion_channel_model_data_dict = {}
    for key, ic_data in ion_channel_models.items():
        # ic_data: IonChannelModel Block
        # ic_data.ion_channel_model: IonChannelModelFromID  # ruff: ignore[commented-out-code]
        conductance = {}
        if hasattr(ic_data, "conductance") and ic_data.ion_channel_model.has_conductance(
            db_client=client
        ):
            conductance = {
                ic_data.ion_channel_model.get_conductance_name(
                    db_client=client
                ): ic_data.conductance
            }
        elif hasattr(
            ic_data, "max_permeability"
        ) and ic_data.ion_channel_model.has_max_permeability(db_client=client):
            conductance = {
                ic_data.ion_channel_model.get_max_permeability_name(
                    db_client=client
                ): ic_data.max_permeability
            }
        ion_channel_model_data_dict[key] = {
            "id": ic_data.ion_channel_model.id_str,
        }
        ion_channel_model_data_dict[key].update(conductance)

    circuit_config_path = stage_sonata_from_config(
        client=client,
        ion_channel_model_data=ion_channel_model_data_dict,
        output_dir=output_dir,
    )

    return MEModelCircuit(name="single_cell", path=str(circuit_config_path))


def _build_memodel_circuit(circuit_config_path: Path) -> MEModelCircuit:
    return MEModelCircuit(name="single_cell", path=str(circuit_config_path))


def stage_memodel_as_circuit(
    *,
    client: Client,
    circuit: MEModelCircuit | MEModelFromID,
    output_dir: Path,
    max_concurrent: int = 1,
) -> MEModelCircuit:
    """Stage a single-neuron ME-model circuit for simulation execution."""
    if isinstance(circuit, MEModelCircuit):
        return circuit

    circuit_config_path = stage_sonata_from_memodel(
        client=client,
        memodel=cast("MEModel", circuit.entity(db_client=client)),
        output_dir=output_dir,
        max_concurrent=max_concurrent,
    )
    return _build_memodel_circuit(circuit_config_path)


def get_simulation_parameters(
    *,
    simulation_backend: SimulationBackend,
    simulation_config_file: Path,
    mechanism_build: MechanismBuild,
) -> SimulationParameters:
    """Return simulation parameters."""
    config_data = load_json(simulation_config_file)

    # Resolve the node set to concrete cells via libsonata rather than reading the raw
    # node sets file. The node set may be defined symbolically (e.g. by population,
    # mtype or synapse_class) or as a compound reference -- in which case it has no
    # explicit "node_id" list -- and it may live in the circuit's node sets or in the
    # simulation's own node_sets_file. libsonata.SimulationConfig resolves the referenced
    # circuit ("network") and manifest variables, and the circuit + simulation node sets
    # are merged for resolution.
    simulation_config = libsonata.SimulationConfig.from_file(str(simulation_config_file))
    node_set_name = simulation_config.node_set
    if not node_set_name:
        msg = "No node set defined in the simulation config."
        raise ValueError(msg)
    num_cells = count_cells_in_simulation_node_set(simulation_config, node_set_name)

    tstop = config_data["run"]["tstop"]

    match simulation_backend:
        case SimulationBackend.bluecellulab:
            return BluecellulabSimulationParameters(
                config_file=simulation_config_file,
                number_of_cells=num_cells,
                stop_time=tstop,
                mechanism_build=cast("NeuronMechanismBuild", mechanism_build),
            )
        case SimulationBackend.neurodamus:
            return NeurodamusSimulationParameters(
                config_file=simulation_config_file,
                number_of_cells=num_cells,
                stop_time=tstop,
                mechanism_build=cast("NeurodamusMechanismBuild", mechanism_build),
            )
        case _:
            msg = f"Unsupported simulation backend {simulation_backend}."
            raise RuntimeError(msg)

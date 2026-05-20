import logging
from pathlib import Path
from typing import cast

from entitysdk import Client, models
from entitysdk.staging.circuit import stage_circuit as stage_circuit_entity
from entitysdk.staging.ion_channel_model import stage_sonata_from_config
from entitysdk.staging.memodel import stage_sonata_from_memodel

from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.memodel_circuit import MEModelCircuit
from obi_one.scientific.library.simulation.schemas import (
    BluecellulabSimulationParameters,
    MechanismBuild,
    NeurodamusMechanismBuild,
    NeurodamusSimulationParameters,
    NeuronMechanismBuild,
    SimulationParameters,
)
from obi_one.types import SimulationBackend
from obi_one.utils.io import load_json

L = logging.getLogger(__name__)


def stage_circuit(*, client: Client, model: models.Circuit, output_dir: Path) -> Circuit:
    """Stage circuit."""
    circuit_config_path: Path = stage_circuit_entity(
        client=client,
        model=model,
        output_dir=output_dir,
    )
    return Circuit(name=cast("str", model.name), path=str(circuit_config_path))


def stage_ion_channel_models_as_circuit(
    *, client: Client, ion_channel_models: dict, output_dir: Path
) -> MEModelCircuit:
    # build ion channel model data dict for staging sonata config
    ion_channel_model_data_dict = {}
    for key, ic_data in ion_channel_models.items():
        # ic_data: IonChannelModel Block
        # ic_data.ion_channel_model: IonChannelModelFromID  # noqa: ERA001
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
) -> MEModelCircuit:
    """Stage a single-neuron ME-model circuit for simulation execution."""
    if isinstance(circuit, MEModelCircuit):
        return circuit

    circuit_config_path = stage_sonata_from_memodel(
        client=client,
        memodel=circuit.entity(db_client=client),
        output_dir=output_dir,
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

    node_set_name = config_data.get("node_set", "All")
    node_sets_file = simulation_config_file.parent / config_data["node_sets_file"]

    node_set_data = load_json(node_sets_file)

    if node_set_name not in node_set_data:
        msg = f"Node set '{node_set_name}' not found in node sets file"
        raise KeyError(msg)

    num_cells = len(node_set_data[node_set_name]["node_id"])
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

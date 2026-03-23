import logging
from pathlib import Path

from entitysdk import Client
from entitysdk.staging.ion_channel_model import stage_sonata_from_config

from obi_one.scientific.library.memodel_circuit import MEModelCircuit
from obi_one.scientific.library.simulation.schemas import SimulationParameters
from obi_one.utils.io import load_json

L = logging.getLogger(__name__)


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


def get_simulation_parameters(
    simulation_config_file: Path, libnrnmech_path: Path
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

    return SimulationParameters(
        config_file=simulation_config_file,
        number_of_cells=num_cells,
        stop_time=tstop,
        libnrnmech_path=libnrnmech_path,
    )

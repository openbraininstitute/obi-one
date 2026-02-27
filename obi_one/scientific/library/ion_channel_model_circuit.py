from pathlib import Path

import entitysdk
from entitysdk.staging.ion_channel_model import stage_sonata_from_config

from obi_one.scientific.library.memodel_circuit import MEModelCircuit
from obi_one.scientific.unions.unions_ion_channel_model import (
    IonChannelModelUnion,
)


# this class should probably be in another module. I just put it here for the time being.
# wanted to put it in ionchannelmodelfromid, but it created circular imports
# should create a module in library for it I guess. ion_channel_model_circuit.py or something
class FakeCircuitFromIonChannelModels:
    id_str: str = "fake_circuit"

    def __init__(self, ion_channel_data: dict[str, IonChannelModelUnion]) -> None:
        """Initialize object."""
        self.ion_channel_data = ion_channel_data

    def stage_circuit(
        self,
        *,
        db_client: entitysdk.client.Client = None,
        dest_dir: Path | None = None,
        entity_cache: bool = False,
    ) -> MEModelCircuit:
        if not entity_cache and dest_dir.exists():
            msg = f"Circuit directory '{dest_dir}' already exists and is not empty."
            raise FileExistsError(msg)

        if (not entity_cache) | (entity_cache and not dest_dir.exists()):
            # build ion channel model data dict for staging sonata config
            ion_channel_model_data_dict = {}
            for key, ic_data in self.ion_channel_data.items():
                # ic_data: IonChannelModel Block
                # ic_data.ion_channel_model: IonChannelModelFromID  # noqa: ERA001
                conductance = {}
                if hasattr(ic_data, "conductance") and ic_data.ion_channel_model.has_conductance(
                    db_client=db_client
                ):
                    conductance = {
                        ic_data.ion_channel_model.get_conductance_name(
                            db_client=db_client
                        ): ic_data.conductance
                    }
                elif hasattr(
                    ic_data, "max_permeability"
                ) and ic_data.ion_channel_model.has_max_permeability(db_client=db_client):
                    conductance = {
                        ic_data.ion_channel_model.get_max_permeability_name(
                            db_client=db_client
                        ): ic_data.max_permeability
                    }
                ion_channel_model_data_dict[key] = {
                    "id": ic_data.ion_channel_model.id_str,
                }
                ion_channel_model_data_dict[key].update(conductance)

            circuit_config_path = stage_sonata_from_config(
                client=db_client,
                ion_channel_model_data=ion_channel_model_data_dict,
                output_dir=dest_dir,
            )
        else:
            circuit_config_path = dest_dir / "circuit_config.json"

        return MEModelCircuit(name="single_cell", path=str(circuit_config_path))

from pathlib import Path

import entitysdk
from entitysdk.staging.ion_channel_model import stage_sonata_from_config

from obi_one.scientific.library.memodel_circuit import MEModelCircuit
from obi_one.scientific.unions.unions_ion_channel_model import (
    IonChannelModelUnion,
)


class CircuitFromIonChannelModels:
    id_str: str = "fake_circuit"

    def __init__(self, ion_channel_data: dict[str, IonChannelModelUnion]) -> None:
        """Initialize object."""
        self.ion_channel_data = ion_channel_data

    def stage_circuit(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
        dest_dir: Path | None = None,
        entity_cache: bool = False,
    ) -> MEModelCircuit:
        if not entity_cache and dest_dir.exists():  # ty:ignore[unresolved-attribute]
            msg = f"Circuit directory '{dest_dir}' already exists and is not empty."
            raise FileExistsError(msg)

        if (not entity_cache) | (entity_cache and not dest_dir.exists()):  # ty:ignore[unresolved-attribute]
            # build ion channel model data dict for staging sonata config
            ion_channel_model_data_dict = {}
            for key, ic_data in self.ion_channel_data.items():
                # ic_data: IonChannelModel Block
                # ic_data.ion_channel_model: IonChannelModelFromID  # noqa: ERA001
                conductance = {}
                if hasattr(ic_data, "conductance") and ic_data.ion_channel_model.has_conductance(
                    db_client=db_client
                ):
                    conductance = {"conductance": ic_data.conductance}
                elif hasattr(
                    ic_data, "max_permeability"
                ) and ic_data.ion_channel_model.has_max_permeability(db_client=db_client):
                    conductance = {"conductance": ic_data.max_permeability}
                ion_channel_model_data_dict[key] = {
                    "id": ic_data.ion_channel_model.id_str,
                }
                ion_channel_model_data_dict[key].update(conductance)

            circuit_config_path = stage_sonata_from_config(
                client=db_client,
                ion_channel_model_data=ion_channel_model_data_dict,
                output_dir=dest_dir,  # ty:ignore[invalid-argument-type]
                # here, use the same radius as the one used in ion channel model building
                radius=12.6157 / 2.0,
            )
        else:
            circuit_config_path = dest_dir / "circuit_config.json"  # ty:ignore[unsupported-operator]

        return MEModelCircuit(name="single_cell", path=str(circuit_config_path))

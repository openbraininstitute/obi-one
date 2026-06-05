import logging
import json

from pathlib import Path
from entitysdk import Client, types, models
from conntility import ConnectivityMatrix

from obi_one.core.task import Task
from obi_one.scientific.library.wire_circuit import write_wired_circuit
from obi_one.scientific.tasks.wire_circuit.config import WireStructuralCircuitSingleConfig
from obi_one.utils.circuit_registration.register import register_asset
from obi_one.utils.circuit_registration.generate import generate_additional_circuit_assets

def circuit_matrix_object(entity_client: Client, circ: models.Circuit, root: Path):
    asset_dict = {
        asset.label: asset for asset in circ.assets
    }
    err_str = f"{circ.id} does not have a ConnectivityMatrix!"
    if circ.id is None or types.AssetLabel.circuit_connectivity_matrices not in asset_dict.keys():
        raise ValueError(err_str)
    matrices_id = asset_dict[types.AssetLabel.circuit_connectivity_matrices].id
    if matrices_id is not None:
        entity_client.download_directory(
            entity_id=circ.id,
            entity_type=models.Circuit,
            asset_id=matrices_id,
            output_path=root
        )
    else:
        raise ValueError(err_str)

    matrices_root = root / asset_dict[types.AssetLabel.circuit_connectivity_matrices].path
    toc_fn = matrices_root / "matrix_config.json"
    with open(toc_fn, "r") as fid:
        toc = json.load(fid)

    # TODO: Selection instead of returning just the first
    if len(toc) < 1:
        raise ValueError(err_str)
    M_path = matrices_root / list(list(toc.values())[0].values())[0]["path"]
    M = ConnectivityMatrix.from_h5(M_path)
    return M

class WireStructuralCircuitTask(Task):
    """Create a structural SONATA circuit from a ConnectivityMatrix.
    Said ConnectivityMatrix is an asset of a `Circuit` object, the 
    SONATA circuit is to be registered as another asset.
    """

    config: WireStructuralCircuitSingleConfig

    def execute(
        self,
        *,
        db_client: Client = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,
    ) -> None:
        if db_client is None:
            err_str = "ConnectivityMatrix download and MEModel access require a working db_client"
            raise ValueError(err_str)
        
        circ = self.config.initialize.circuit.entity(db_client=db_client)
        circ_name = circ.name or "custom_circuit"
        circuit_root = Path(self.config.coordinate_output_root) / circ_name / "SONATA"

        M = circuit_matrix_object(db_client, circ,
                                  Path(self.config.coordinate_output_root) / circ_name)

        circuit_config_path = write_wired_circuit(
            M,
            db_client,
            circuit_root,
            self.config.initialize.node_population_name,
            self.config.initialize.edge_population_name
        )
        print("Register SONATA!")
        register_asset(db_client, circuit_root, "sonata_circuit", circ, dry_run=False)
        print("Create and register additional assets!")
        generate_additional_circuit_assets(
            circuit_config_path, self.config.initialize.edge_population_name, db_client, circ
        )
        



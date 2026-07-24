from pathlib import Path
from typing import ClassVar

import entitysdk
from entitysdk.models import SimulatableExtracellularRecordingArray
from entitysdk.models.entity import Entity
from entitysdk.result import IteratorResultError
from entitysdk.types import AssetLabel
from entitysdk.utils.filesystem import create_dir
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import EntityFromID
from obi_one.core.exception import OBIONEError


class SimulatableExtracellularRecordingArrayFromID(EntityFromID):
    entitysdk_class: ClassVar[type[Entity]] = SimulatableExtracellularRecordingArray
    _entity: SimulatableExtracellularRecordingArray | None = PrivateAttr(default=None)

    def download_electrode_file(
        self,
        dest_dir: Path = Path(),
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
        file_name: str | None = None,
    ) -> Path:
        """Download the array's weight matrix, i.e. the SONATA LFP report `electrodes_file`.

        The file holds, per electrode, the weight applied to the membrane current of every
        segment of every neuron in the circuit the array was built for.

        Args:
            dest_dir: Directory to download into. Created if it does not exist.
            db_client: Client used to fetch the entity and its asset.
            file_name: Name to give the downloaded file. Defaults to the asset's own name.

        Returns:
            Path of the downloaded file.
        """
        output_dir = create_dir(dest_dir)
        try:
            downloaded = db_client.download_assets(
                self.entity(db_client=db_client),
                selection={"label": AssetLabel.electrode_array_weight_matrix},
                output_path=output_dir,
            ).one()
        except IteratorResultError as error:
            msg = (
                f"Expected exactly one '{AssetLabel.electrode_array_weight_matrix}' asset on "
                f"extracellular recording array '{self.id_str}': {error}"
            )
            raise OBIONEError(msg) from error

        if file_name is None or downloaded.path.name == file_name:
            return downloaded.path

        return downloaded.path.replace(output_dir / file_name)

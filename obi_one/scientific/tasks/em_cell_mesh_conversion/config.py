from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import Field, PrivateAttr

from obi_one.core.base import OBIBaseModel


class EMCellMeshConversionSingleConfig(OBIBaseModel):
    """Converts the OBJ surface mesh of a draft EM cell mesh to a Draco GLB."""

    idx: int = 0
    scan_output_root: Path = Path()
    coordinate_output_root: Path = Path()

    em_cell_mesh_id: UUID = Field(description="The EM cell mesh whose OBJ asset is converted.")

    _single_entity: Any = PrivateAttr(default=None)

    @property
    def single_entity(self) -> Any:
        return self._single_entity

    def set_single_entity(self, entity: Any) -> None:
        self._single_entity = entity

import io
import logging
import os
import tempfile
from pathlib import Path
from typing import ClassVar

import entitysdk
import morphio
import neurom
from entitysdk._server_schemas import AssetLabel, ContentType  # NOQA: PLC2701
from entitysdk.exception import EntitySDKError
from entitysdk.models import CellMorphology, EMCellMesh, TaskActivity, TaskConfig
from entitysdk.models.cell_morphology_protocol import PlaceholderCellMorphologyProtocol
from entitysdk.models.entity import Entity
from entitysdk.types import CellMorphologyProtocolDesign, EntityType, TaskActivityType
from morph_spines import MorphologyWithSpines, load_morphology_with_spines
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import EntityFromID, LoadAssetMethod

L = logging.getLogger(__name__)

_MORPHOLOGY_ASSET_FORMATS = (
    (ContentType.application_asc, ".asc"),
    (ContentType.application_swc, ".swc"),
    (ContentType.application_x_hdf5, ".h5"),
)


class CellMorphologyFromID(EntityFromID):
    entitysdk_class: ClassVar[type[Entity]] = CellMorphology
    _entity: CellMorphology | None = PrivateAttr(default=None)
    _swc_file_path: Path | None = PrivateAttr(default=None)
    _neurom_morphology: neurom.core.Morphology | None = PrivateAttr(default=None)
    _morphio_morphology: morphio.Morphology | None = PrivateAttr(default=None)
    _swc_file_content: str | None = PrivateAttr(default=None)

    def swc_file_content(self, db_client: entitysdk.client.Client = None) -> None:  # ty:ignore[invalid-parameter-default]
        """Function for downloading SWC files of a morphology into memory."""
        if self._swc_file_content is None:
            for asset in self.entity(db_client=db_client).assets:
                if asset.content_type == "application/swc":
                    load_asset_method = LoadAssetMethod.MEMORY
                    if load_asset_method == LoadAssetMethod.MEMORY:
                        L.info("Downloading SWC file for morphology...")

                        # Download the content into memory
                        if asset.id is None:
                            msg = "Asset must have an id"
                            raise ValueError(msg)
                        content = db_client.download_content(
                            entity_id=self.entity(db_client=db_client).id,  # ty:ignore[invalid-argument-type]
                            entity_type=self.entitysdk_type,
                            asset_id=asset.id,
                        ).decode(encoding="utf-8")

                        self._swc_file_content = content
                        break

            if self._swc_file_content is None:
                msg = "No valid application/asc asset found for morphology."
                raise ValueError(msg)

        return self._swc_file_content  # ty:ignore[invalid-return-type]

    def neurom_morphology(
        self,
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
    ) -> neurom.core.Morphology:
        """Getter for the neurom_morphology property.

        Downloads the application/asc asset if not already downloaded
        and loads it using neurom.load_morphology.
        """
        if self._neurom_morphology is None:
            self._neurom_morphology = neurom.load_morphology(
                io.StringIO(self.swc_file_content(db_client)), reader="swc"
            )
        return self._neurom_morphology

    def has_source_mesh(self, db_client: entitysdk.client.Client = None) -> bool:  # ty:ignore[invalid-parameter-default]
        """Does the cell morphology originate from an EMCellMesh?

        Test if there is a Skeletonization Task associated with the
        CellMorphology and an EMCellMesh is available from that task.
        """
        morph_entity = self.entity(db_client=db_client)
        if not isinstance(morph_entity, CellMorphology):
            return False
        cm_protocol = morph_entity.cell_morphology_protocol
        if cm_protocol is None:
            return False
        if (isinstance(cm_protocol, PlaceholderCellMorphologyProtocol)) or (
            cm_protocol.protocol_design != CellMorphologyProtocolDesign.electron_microscopy
        ):
            return False

        activity = db_client.search_entity(
            entity_type=TaskActivity,
            query={
                "task_activity_type": TaskActivityType.skeletonization__execution,
                "generated__id": morph_entity.id,
            },
        ).one_or_none()
        if activity is None:
            return False
        if (
            (activity.used is None)
            or (len(activity.used) != 1)
            or (activity.used[0].type != EntityType.task_config)
            or (activity.used[0].id is None)
        ):
            return False
        task_cfg = db_client.get_entity(entity_id=activity.used[0].id, entity_type=TaskConfig)
        return (
            (task_cfg.inputs is not None)
            and (len(task_cfg.inputs) == 1)
            and (task_cfg.inputs[0].type == EntityType.em_cell_mesh)
        )

    def source_mesh_entity(self, db_client: entitysdk.client.Client = None) -> EMCellMesh:  # ty:ignore[invalid-parameter-default]
        """EMCellMesh entity that the morphology originates from.

        For CellMorphologies that were created from EMCellMeshes via skeletonization,
        this returns the EMCellMesh entity it originates from. Raises EntitySDKError
        for CellMorphologies that were created by other methods.
        """
        if not self.has_source_mesh(db_client=db_client):
            err_str = "This CellMorphology does not seem to originate from an EMCellMesh!"
            raise EntitySDKError(err_str)

        morph_entity = self.entity(db_client=db_client)
        activity = db_client.search_entity(
            entity_type=TaskActivity,
            query={
                "task_activity_type": TaskActivityType.skeletonization__execution,
                "generated__id": morph_entity.id,
            },
        ).one_or_none()
        task_cfg = db_client.get_entity(entity_id=activity.used[0].id, entity_type=TaskConfig)  # ty:ignore[invalid-argument-type, not-subscriptable, unresolved-attribute]
        source_mesh = db_client.get_entity(entity_id=task_cfg.inputs[0].id, entity_type=EMCellMesh)  # ty:ignore[invalid-argument-type, not-subscriptable]
        return source_mesh

    def write_spiny_neuron_h5(
        self,
        path_to: Path | str,
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
    ) -> None:
        entity = self.entity(db_client=db_client)
        for asset in entity.assets:
            if (asset.label == AssetLabel.morphology_with_spines) and (
                asset.content_type == ContentType.application_x_hdf5
            ):
                if asset.id is None:
                    msg = "Asset must have an id"
                    raise ValueError(msg)
                db_client.download_file(
                    entity_id=entity.id,  # ty:ignore[invalid-argument-type]
                    entity_type=self.entitysdk_class,
                    asset_id=asset.id,
                    output_path=str(path_to),  # ty:ignore[invalid-argument-type]
                )
                return
        err_str = "Entity does not have a spiny morphology asset!"
        raise EntitySDKError(err_str)

    def spiny_morphology(
        self, db_client: entitysdk.client.Client | None = None, path: os.PathLike | None = None
    ) -> MorphologyWithSpines:
        entity = self.entity(db_client=db_client)  # ty:ignore[invalid-argument-type]
        if path is None:
            path = Path.cwd()
        if not isinstance(path, Path):
            path = Path(path)
        if Path(path).is_dir():
            path = path / (entity.name + ".h5")  # NOQA: PLR6104  # ty:ignore[unsupported-operator]

        self.write_spiny_neuron_h5(path, db_client)  # ty:ignore[invalid-argument-type]
        spiny_morph = load_morphology_with_spines(str(path))
        return spiny_morph

    def morphio_morphology(self, db_client: entitysdk.client.Client = None) -> morphio.Morphology:  # ty:ignore[invalid-parameter-default]
        """Getter for the morphio_morphology property.

        Download a supported morphology asset and load it with MorphIO.
        """
        if self._morphio_morphology is None:
            entity = self.entity(db_client=db_client)
            for content_type, suffix in _MORPHOLOGY_ASSET_FORMATS:
                asset = next(
                    (asset for asset in entity.assets if asset.content_type == content_type), None
                )
                if asset is None:
                    continue
                if asset.id is None:
                    msg = "Morphology asset must have an id."
                    raise ValueError(msg)
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / f"morphology{suffix}"
                    db_client.download_file(
                        entity_id=entity.id,  # ty:ignore[invalid-argument-type]
                        entity_type=self.entitysdk_class,
                        asset_id=asset.id,
                        output_path=path,
                    )
                    self._morphio_morphology = morphio.Morphology(path)
                break

            if self._morphio_morphology is None:
                msg = "Morphology entity has no ASC, SWC, or H5 morphology asset."
                raise EntitySDKError(msg)

        return self._morphio_morphology

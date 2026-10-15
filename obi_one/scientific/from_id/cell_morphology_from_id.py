import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from entitysdk.client import Client as DBClient
from entitysdk.exception import EntitySDKError
from entitysdk.models import (
    BrainRegion,
    CellMorphology,
    EMCellMesh,
    Species,
    TaskActivity,
    TaskConfig,
)
from entitysdk.types import (
    AssetLabel,
    CellMorphologyProtocolDesign,
    ContentType,
    EntityType,
    TaskActivityType,
)

from obi_one.core.entity_from_id import EntityFromID
from obi_one.db_sdk.db_sdk import select_asset_content

if TYPE_CHECKING:
    import morphio
    import neurom
    from morph_spines import MorphologyWithSpines


class CellMorphologyFromID(EntityFromID[CellMorphology]):
    """Reference to a CellMorphology entity."""

    _entitysdk_type: type[CellMorphology] = CellMorphology
    _neurom_morphology: Any = None
    _morphio_morphology: Any = None

    def neurom_morphology(self, db_client: DBClient) -> "neurom.core.Morphology":
        """Load the morphology's SWC asset as a Neurom morphology."""
        import neurom  # ruff: ignore[import-outside-top-level]

        if self._neurom_morphology is None:
            swc_content = select_asset_content(
                client=db_client,
                entity=self.entity(db_client=db_client),
                selection={
                    "content_type": ContentType.application_swc,
                    "label": AssetLabel.morphology,
                },
            ).decode("utf-8")
            self._neurom_morphology = neurom.load_morphology(swc_content, reader="swc")
        return self._neurom_morphology

    def metadata_entities(self, db_client: DBClient) -> tuple[Species, BrainRegion]:
        """Return the species and brain-region entities linked to the morphology."""
        entity = self.entity(db_client=db_client)

        subject = entity.subject
        if subject is None:
            msg = f"CellMorphology {self.id_str} has no subject relationship."
            raise EntitySDKError(msg)

        species = subject.species
        if species is None:
            msg = f"CellMorphology {self.id_str} has no subject.species relationship."
            raise EntitySDKError(msg)

        brain_region = entity.brain_region
        if brain_region is None:
            msg = f"CellMorphology {self.id_str} has no brain_region relationship."
            raise EntitySDKError(msg)

        return species, brain_region

    def has_source_mesh(self, db_client: DBClient) -> bool:
        """Does the cell morphology originate from an EMCellMesh?

        Test if there is a Skeletonization Task associated with the
        CellMorphology and an EMCellMesh is available from that task.
        """
        return _morphology_has_source_mesh(self.entity(db_client=db_client), db_client)

    def source_mesh_entity(self, db_client: DBClient) -> EMCellMesh:
        """EMCellMesh entity that the morphology originates from.

        For CellMorphologies that were created from EMCellMeshes via skeletonization,
        this returns the EMCellMesh entity it originates from. Raises EntitySDKError
        for CellMorphologies that were created by other methods.
        """
        return _morphology_source_mesh_entity(self.entity(db_client=db_client), db_client)

    def spiny_morphology(
        self, db_client: DBClient, path: str | os.PathLike | None = None
    ) -> "MorphologyWithSpines":
        from morph_spines import load_morphology_with_spines  # ruff: ignore[import-outside-top-level]

        entity = self.entity(db_client=db_client)

        if path is None:
            path = Path.cwd()
        if not isinstance(path, Path):
            path = Path(path)
        if path.is_dir():
            path /= f"{entity.name}.h5"

        db_client.fetch_assets(
            entity,
            selection={
                "content_type": ContentType.application_x_hdf5,
                "label": AssetLabel.morphology_with_spines,
            },
            output_path=Path(path),
        ).one()

        return load_morphology_with_spines(str(path))

    def morphio_morphology(self, db_client: DBClient) -> "morphio.Morphology":
        """Download a supported morphology asset and load it with MorphIO."""
        import tempfile  # ruff: ignore[import-outside-top-level]

        import morphio  # ruff: ignore[import-outside-top-level]

        if self._morphio_morphology is None:
            with tempfile.NamedTemporaryFile(suffix=".h5") as tmp:
                path = Path(tmp.name)
                db_client.fetch_assets(
                    self.entity(db_client=db_client),
                    selection={
                        "content_type": ContentType.application_x_hdf5,
                        "label": AssetLabel.morphology,
                    },
                    output_path=path,
                ).one()
                self._morphio_morphology = morphio.Morphology(
                    path, options=morphio.Option.nrn_order
                )
        return self._morphio_morphology


def _morphology_has_source_mesh(entity: CellMorphology, db_client: DBClient) -> bool:
    """Return whether the morphology originates from an EMCellMesh via skeletonization."""
    from entitysdk.models.cell_morphology_protocol import (  # ruff: ignore[import-outside-top-level]
        PlaceholderCellMorphologyProtocol,
    )

    if not isinstance(entity, CellMorphology):
        return False
    cm_protocol = entity.cell_morphology_protocol
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
            "generated__id": entity.id,
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


def _morphology_source_mesh_entity(entity: CellMorphology, db_client: DBClient) -> EMCellMesh:
    """Return the EMCellMesh this morphology was skeletonized from.

    Raises:
        EntitySDKError: If the morphology does not originate from an EMCellMesh.
    """
    if not _morphology_has_source_mesh(entity, db_client):
        err_str = "This CellMorphology does not seem to originate from an EMCellMesh!"
        raise EntitySDKError(err_str)

    activity = db_client.search_entity(
        entity_type=TaskActivity,
        query={
            "task_activity_type": TaskActivityType.skeletonization__execution,
            "generated__id": entity.id,
        },
    ).one_or_none()
    task_cfg = db_client.get_entity(entity_id=activity.used[0].id, entity_type=TaskConfig)  # ty:ignore[not-subscriptable, unresolved-attribute]
    return db_client.get_entity(entity_id=task_cfg.inputs[0].id, entity_type=EMCellMesh)  # ty:ignore[not-subscriptable]

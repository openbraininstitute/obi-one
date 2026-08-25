import tempfile
from http import HTTPStatus
from pathlib import Path
from uuid import UUID

import libsonata
import morphio
import numpy as np
from entitysdk.client import Client
from entitysdk.exception import EntitySDKError
from entitysdk.models import CellMorphology, Circuit, MEModel
from entitysdk.types import AssetLabel, CircuitScale, ContentType
from fastapi import HTTPException

from app.errors import ApiErrorCode
from app.logger import L
from app.schemas.circuit_visualization import (
    MorphoViewerTreeItemType,
    MorphPath,
    Node,
    Nodes,
    SectionDict,
    SynapseGroup,
)


def circuit_asset_id(client: Client, circuit_id: UUID) -> UUID:
    try:
        circuit = client.get_entity(entity_id=circuit_id, entity_type=Circuit)
    except EntitySDKError as e:
        L.exception(e)
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Couldn't fetch the circuit",
            },
        ) from e

    if circuit.scale not in {CircuitScale.single, CircuitScale.pair, CircuitScale.small}:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Circuit's scale should be 'single', 'pair' or 'small'",
            },
        )

    try:
        asset = client.select_assets(
            circuit,
            selection={
                "label": "sonata_circuit",
            },
        ).one()

    except EntitySDKError as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Circuit is missing a sonata_circuit asset",
            },
        ) from e

    return asset.id


def get_population_nodes(  # ruff: ignore[too-many-locals]
    population_name: str,
    db_client: Client,
    circuit_id: UUID,
    asset_id: UUID,
    parent_dir: Path,
    asset_path: Path,
    morphologies_path: MorphPath,
) -> Nodes:
    nodes_file_path = parent_dir / asset_path

    try:
        db_client.download_file(
            entity_id=circuit_id,
            entity_type=Circuit,
            asset_id=asset_id,
            output_path=nodes_file_path,
            asset_path=asset_path,
        )
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Missing file {asset_path}",
            },
        ) from e

    try:  # ruff: ignore[too-many-statements-in-try-clause]
        storage = libsonata.NodeStorage(str(nodes_file_path))
        population = storage.open_population(population_name)

        selection = libsonata.Selection([(0, population.size)])

        x = population.get_attribute("x", selection)
        y = population.get_attribute("y", selection)
        z = population.get_attribute("z", selection)

        qx = population.get_attribute("orientation_x", selection)
        qy = population.get_attribute("orientation_y", selection)
        qz = population.get_attribute("orientation_z", selection)
        qw = population.get_attribute("orientation_w", selection)

        morph_files = population.get_attribute("morphology", selection)

        nodes_list = []
        m_path = morphologies_path.path.relative_to(parent_dir)
        for i in range(population.size):
            m_name = morph_files[i]
            m_file = m_path if m_path.suffix else m_path / f"{m_name}.{morphologies_path.format}"

            nodes_list.append(
                Node(
                    position=(float(x[i]), float(y[i]), float(z[i])),
                    orientation=(float(qx[i]), float(qy[i]), float(qz[i]), float(qw[i])),
                    morphology_file=str(m_file),
                    morphology_name=m_name,
                )
            )

    except HTTPException:
        raise
    except Exception as e:
        L.exception(f"Error reading population {population_name}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": f"Couldn't get nodes from population {population_name}",
            },
        ) from e

    return nodes_list


def resolve_morph_path(
    population_name: str,
    config: libsonata.CircuitConfig,
) -> MorphPath:
    pop_properties = config.node_population_properties(population_name)
    if pop_properties.morphologies_dir:
        return MorphPath(path=Path(pop_properties.morphologies_dir), format="swc")

    alternate_morphologies: dict = pop_properties.alternate_morphology_formats

    path_item = next(iter(alternate_morphologies.items()), None)

    if path_item:
        format_ = "asc" if path_item[0] == "neurolucida-asc" else "h5"
        return MorphPath(path=Path(path_item[1]), format=format_)

    m = "No morphologies found"
    raise ValueError(m)


def get_nodes(
    config: libsonata.CircuitConfig,
    parent_path: Path,
    db_client: Client,
    circuit_id: UUID,
    asset_id: UUID,
) -> Nodes:
    all_nodes = []
    try:  # ruff: ignore[too-many-statements-in-try-clause]
        for pop_name in config.node_populations:
            pop_properties = config.node_population_properties(pop_name)

            if pop_properties.type != "biophysical":
                continue

            nodes_file_path = Path(pop_properties.elements_path)
            asset_path = nodes_file_path.relative_to(parent_path)

            morph_path = resolve_morph_path(pop_name, config)

            all_nodes += get_population_nodes(
                pop_name,
                db_client,
                circuit_id,
                asset_id,
                parent_path,
                asset_path,
                morph_path,
            )

    except HTTPException:
        raise
    except Exception as e:
        L.exception(e)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": "Error while reading circuit's nodes",
            },
        ) from e
    return all_nodes


def download_circuit_config(
    client: Client, circuit_id: UUID, asset_id: UUID, directory: Path
) -> libsonata.CircuitConfig:
    circuit_config = Path("circuit_config.json")
    file_path = directory / circuit_config

    try:
        client.download_file(
            entity_id=circuit_id,
            entity_type=Circuit,
            asset_id=asset_id,
            output_path=file_path,
            asset_path=circuit_config,
        )

        return libsonata.CircuitConfig(file_path.read_text(), str(directory))

    except libsonata.SonataError as e:
        L.error(f"Sonata parsing error: {e}")
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Invalid SONATA circuit configuration",
            },
        ) from e

    except Exception as e:
        L.exception(e)
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Couldn't get circuit_config.json asset",
            },
        ) from e


def load_morphology(path: Path, morph_name: str | None) -> morphio.Morphology:
    """Load a circuit morphology in NEURON-compatible section order.

    ``nrn_order`` is required, not cosmetic: a section's id is its position in the
    section list, so a different ordering yields different ids for the same branch.
    """
    try:
        return morphio.Morphology(path, options=morphio.Option.nrn_order)
    except morphio.MorphioError:
        collection = morphio.Collection(path.as_posix())
        return collection.load(morph_name, morphio.Option.nrn_order)


def get_morphology(
    parent_dir: Path,
    client: Client,
    circuit_id: UUID,
    asset_id: UUID,
    morph_path: Path,
    morph_name: str | None,
) -> morphio.Morphology:
    parent_dir = parent_dir.resolve()
    output_path = (parent_dir / morph_path).resolve()

    if not output_path.is_relative_to(parent_dir):
        raise HTTPException(status_code=400, detail="Invalid morphology path")

    if not output_path.exists():
        try:
            client.download_file(
                entity_type=Circuit,
                output_path=output_path,
                entity_id=circuit_id,
                asset_id=asset_id,
                asset_path=morph_path,
            )
        except Exception as e:
            raise HTTPException(status_code=404, detail="Morphology not found") from e

    try:
        return load_morphology(output_path, morph_name)

    except Exception as e:
        msg = f"Could not parse morphology {morph_path} {morph_name}"
        raise HTTPException(status_code=500, detail=msg) from e


def _map_section_type(sec_type: morphio.SectionType) -> MorphoViewerTreeItemType:
    mapping = {
        morphio.SectionType.soma: MorphoViewerTreeItemType.Soma,
        morphio.SectionType.basal_dendrite: MorphoViewerTreeItemType.BasalDendrite,
        morphio.SectionType.apical_dendrite: MorphoViewerTreeItemType.ApicalDendrite,
        morphio.SectionType.axon: MorphoViewerTreeItemType.Axon,
    }
    return mapping.get(sec_type, MorphoViewerTreeItemType.Unknown)


SOMA_SONATA_SECTION_ID = 0


def sonata_section_id(morphio_section_id: int) -> int:
    """Convert a morphio section id into a SONATA global section id.

    SONATA reserves 0 for the soma and numbers neurites from 1, while morphio keeps
    the soma aside and numbers neurites from 0. The morphology-location blocks undo
    this with ``morphology.section(section_id - 1)``.
    """
    return morphio_section_id + 1


def get_morphology_data(morphology: morphio.Morphology) -> list[SectionDict]:
    sections: list[SectionDict] = []

    soma = morphology.soma
    has_soma = soma is not None and len(soma.points) > 0

    if has_soma:
        sections.append(
            {
                "id": "soma",
                "sonata_section_id": SOMA_SONATA_SECTION_ID,
                "parent_id": None,
                "type": MorphoViewerTreeItemType.Soma,
                "points": soma.points.tolist(),
                "radii": (np.array(soma.diameters) / 2.0).tolist(),
            }
        )

    for section in morphology.iter():
        if section.is_root:  # ruff: ignore[if-else-block-instead-of-if-exp]
            parent_id = "soma" if has_soma else None
        else:
            parent_id = str(section.parent.id)

        sections.append(
            {
                "id": str(section.id),
                "sonata_section_id": sonata_section_id(section.id),
                "parent_id": parent_id,
                "type": _map_section_type(section.type),
                "points": section.points.tolist(),
                "radii": (np.array(section.diameters) / 2.0).tolist(),
            }
        )

    return sections


_MORPHOLOGY_ASSET_TYPES = (
    (ContentType.application_swc, ".swc"),
    (ContentType.application_x_hdf5, ".h5"),
    (ContentType.application_asc, ".asc"),
)


def _load_morphology_content(content: bytes, suffix: str) -> morphio.Morphology:
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(content)
        tmp.flush()
        return morphio.Morphology(tmp.name, options=morphio.Option.nrn_order)


def load_cell_morphology(client: Client, morphology: CellMorphology) -> morphio.Morphology:
    """Load a cell morphology asset in NEURON-compatible section order.

    Uses ``nrn_order`` to match :func:`load_morphology`. A section's id is its position in the
    section list, so both must agree for an id to mean the same branch.

    Args:
        client: entitycore client used to download the asset.
        morphology: The cell morphology whose asset to load.

    Returns:
        The morphology, sections ordered as NEURON orders them.

    Raises:
        ValueError: If the morphology or its asset has no id, or carries no SWC, H5 or ASC asset.
    """
    if morphology.id is None:
        msg = "Cell morphology is missing an id."
        raise ValueError(msg)

    assets = morphology.assets or []
    for content_type, suffix in _MORPHOLOGY_ASSET_TYPES:
        asset = next(
            (
                asset
                for asset in assets
                if asset.content_type == content_type and asset.label == AssetLabel.morphology
            ),
            None,
        )
        if asset is None:
            continue
        if asset.id is None:
            msg = "Morphology asset is missing an id."
            raise ValueError(msg)

        content = client.download_content(
            entity_id=morphology.id,
            entity_type=CellMorphology,
            asset_id=asset.id,
        )
        return _load_morphology_content(content, suffix)

    msg = "Cell morphology has no supported SWC, H5, or ASC asset."
    raise ValueError(msg)


def memodel_cell_morphology(client: Client, memodel: MEModel) -> CellMorphology:
    """Return the MEModel's cell morphology, re-fetching it if its assets were not embedded.

    Args:
        client: entitycore client used for the re-fetch.
        memodel: The MEModel whose morphology to resolve.

    Returns:
        The cell morphology, with its assets populated.

    Raises:
        ValueError: If the linked morphology has no id.
    """
    morphology = memodel.morphology
    if morphology.assets or []:
        return morphology

    if morphology.id is None:
        msg = "MEModel morphology is missing an id."
        raise ValueError(msg)
    return client.get_entity(entity_id=morphology.id, entity_type=CellMorphology)


def load_memodel_morphology(client: Client, memodel: MEModel) -> morphio.Morphology:
    """Load an MEModel's morphology in NEURON-compatible section order.

    Args:
        client: entitycore client used to resolve and download the morphology.
        memodel: The MEModel to load.

    Returns:
        The morphology, sections ordered as NEURON orders them. Propagates ``ValueError`` when
        the morphology cannot be resolved or carries no usable asset.
    """
    return load_cell_morphology(client, memodel_cell_morphology(client, memodel))


_AFFERENT_SURFACE_ATTRIBUTES = (
    "afferent_surface_x",
    "afferent_surface_y",
    "afferent_surface_z",
)
_SECTION_ID_ATTRIBUTE = "afferent_section_id"


def _has_afferent_surface(population: libsonata.EdgePopulation) -> bool:
    """Whether this population records where on the target's surface each synapse sits.

    A purely functional connectome carries connectivity without geometry; there is nothing to
    draw for those.
    """
    names = set(population.attribute_names)
    return all(name in names for name in (*_AFFERENT_SURFACE_ATTRIBUTES, _SECTION_ID_ATTRIBUTE))


def _resolve_edge_path(parent_dir: Path, elements_path: str) -> Path:
    """Place an edge file inside the working directory, refusing anything that escapes it.

    The path comes from the circuit's own config and is used as a download target, so a ``..``
    or absolute path would write wherever it pointed. Mirrors the guard in :func:`get_morphology`.

    Raises:
        HTTPException: 400 if the path resolves outside ``parent_dir``.
    """
    edges_path = (parent_dir / elements_path).resolve()
    if not edges_path.is_relative_to(parent_dir):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Invalid edge file path",
            },
        )
    return edges_path


def _fetch_edge_file(
    client: Client, circuit_id: UUID, asset_id: UUID, parent_dir: Path, edges_path: Path
) -> bool:
    """Download one edge file into the working directory, if it is not already there.

    The asset arrives a file at a time, so each edge file is asked for by name.

    Returns:
        True if the file is present afterwards; False if it could not be fetched, which leaves
        the circuit drawable without its synapses.
    """
    if edges_path.exists():
        return True
    try:
        client.download_file(
            entity_id=circuit_id,
            entity_type=Circuit,
            asset_id=asset_id,
            output_path=edges_path,
            asset_path=edges_path.relative_to(parent_dir),
        )
    except Exception as exc:  # ruff: ignore[blind-except]
        L.warning(f"Could not download edge file {edges_path}: {exc}")
        return False

    # A download can report success and write nothing; failing here beats a raw HDF5 error.
    if not edges_path.exists():
        L.warning(f"Edge file {edges_path} was not written by the download.")
        return False
    return True


def get_afferent_synapses(
    config: libsonata.CircuitConfig,
    parent_dir: Path,
    client: Client,
    circuit_id: UUID,
    asset_id: UUID,
) -> list[SynapseGroup]:
    """Afferent synapse positions for every edge population that records them.

    Read from the same SONATA circuit as the morphologies, so a synapse and the branch it sits
    on come from one source.

    Args:
        config: The circuit's SONATA config.
        parent_dir: Working directory the edge files are downloaded into.
        client: entitycore client used to fetch them.
        circuit_id: Circuit the asset belongs to.
        asset_id: The circuit's ``sonata_circuit`` asset.

    Returns:
        One group per drawable edge population. Empty when the circuit records connectivity
        without geometry, which is not an error. Raises ``HTTPException`` (400) if an edge path
        escapes ``parent_dir``.
    """
    groups: list[SynapseGroup] = []

    parent_dir = parent_dir.resolve()

    for population_name in config.edge_populations:
        properties = config.edge_population_properties(population_name)
        edges_path = _resolve_edge_path(parent_dir, properties.elements_path)
        if not _fetch_edge_file(client, circuit_id, asset_id, parent_dir, edges_path):
            continue

        storage = libsonata.EdgeStorage(str(edges_path))
        population = storage.open_population(population_name)
        if not _has_afferent_surface(population):
            L.info(f"Edge population {population_name!r} has no afferent surface positions.")
            continue

        selection = libsonata.Selection([(0, population.size)])
        xs, ys, zs = (
            population.get_attribute(name, selection) for name in _AFFERENT_SURFACE_ATTRIBUTES
        )
        section_ids = population.get_attribute(_SECTION_ID_ATTRIBUTE, selection)

        coordinates: list[float] = []
        for x, y, z in zip(xs, ys, zs, strict=True):
            coordinates.extend((float(x), float(y), float(z)))

        groups.append(
            SynapseGroup(
                population_name=population_name,
                coordinates=coordinates,
                section_ids=[int(section_id) for section_id in section_ids],
                target_node_ids=[int(node_id) for node_id in population.target_nodes(selection)],
            )
        )

    return groups

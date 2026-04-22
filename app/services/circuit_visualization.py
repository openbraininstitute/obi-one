from http import HTTPStatus
from pathlib import Path
from uuid import UUID

import libsonata
import morphio
import numpy as np
from entitysdk.client import Client
from entitysdk.exception import EntitySDKError
from entitysdk.models import Circuit
from entitysdk.types import CircuitScale
from fastapi import HTTPException

from app.errors import ApiErrorCode
from app.logger import L
from app.schemas.circuit_visualization import Morphology, MorphPath, NeuronSectionInfo, Node, Nodes

MAX_NODES = 10


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

    if circuit.scale not in {CircuitScale.small, CircuitScale.pair}:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Circuit's scale should be 'small' or 'pair'",
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


def check_node_limit(total_nodes: int, population_size: int) -> None:
    if total_nodes + population_size > MAX_NODES:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Circuit has too many nodes for visualization (limit: 10)",
            },
        )


def get_population_nodes(  # noqa: PLR0914
    population_name: str,
    db_client: Client,
    circuit_id: UUID,
    asset_id: UUID,
    parent_dir: Path,
    asset_path: Path,
    morphologies_path: MorphPath,
    total_nodes: int,
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

    try:
        storage = libsonata.NodeStorage(str(nodes_file_path))
        population = storage.open_population(population_name)

        check_node_limit(total_nodes, population.size)

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
            try:
                morph = get_morphology(parent_dir, db_client, circuit_id, asset_id, m_file, m_name)

                soma_diameters = morph.soma.diameters  # ty:ignore[unresolved-attribute]
                radius = float(np.mean(soma_diameters) / 2.0) if len(soma_diameters) > 0 else 0.0

                if len(soma_diameters) == 0:
                    radius = 0.0

            except Exception as e:  # noqa: BLE001
                L.warning(e.__cause__)
                radius = None

            nodes_list.append(
                Node(
                    position=(float(x[i]), float(y[i]), float(z[i])),
                    orientation=(float(qx[i]), float(qy[i]), float(qz[i]), float(qw[i])),
                    morphology_file=str(m_file),
                    morphology_name=m_name,
                    soma_radius=radius,
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
    try:
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
                len(all_nodes),
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
    try:
        return morphio.Morphology(path)
    except morphio.MorphioError:
        collection = morphio.Collection(path.as_posix())
        return collection.load(morph_name)


def get_morphology(
    parent_dir: Path,
    client: Client,
    circuit_id: UUID,
    asset_id: UUID,
    morph_path: Path,
    morph_name: str | None,
) -> Morphology:
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


SWC_TYPES = {
    morphio.SectionType.soma: "soma",
    morphio.SectionType.axon: "axon",
    morphio.SectionType.basal_dendrite: "dend",
    morphio.SectionType.apical_dendrite: "apic",
}


def get_morphology_data(morphology) -> Morphology:  # noqa: PLR0914, ANN001
    """Parses an morphology filefile into a segment-based dictionary optimized for visualization."""
    section_start_distances: dict[int, float] = {sec.id: 0.0 for sec in morphology.sections}

    def walk_tree_for_distances(section: morphio.Section, current_path_distance: float) -> None:
        section_start_distances[section.id] = current_path_distance

        points = section.points
        vectors = np.diff(points, axis=0)
        section_length = np.sum(np.linalg.norm(vectors, axis=1))

        for child in section.children:
            walk_tree_for_distances(child, current_path_distance + section_length)

    for root_section in morphology.root_sections:
        walk_tree_for_distances(root_section, 0.0)

    morphology_data: Morphology = {}

    for section in morphology.sections:
        base_name = SWC_TYPES.get(section.type, "section")
        section_key = f"{base_name}[{section.id}]"
        points = section.points
        diameters = section.diameters

        starts = points[:-1]
        ends = points[1:]

        directions = ends - starts
        segment_lengths = np.linalg.norm(directions, axis=1)
        midpoints = (starts + ends) / 2.0

        start_dist = section_start_distances[section.id]
        cumulative_internal_lengths = np.cumsum(segment_lengths)
        seg_distances = start_dist + np.insert(cumulative_internal_lengths[:-1], 0, 0)
        parent_id = section.parent.id if not section.is_root else -1

        num_segments = len(segment_lengths)

        morphology_data[section_key] = NeuronSectionInfo(
            index=section.id,
            parent_index=parent_id,
            name=section_key,
            nseg=num_segments,
            distance_from_soma=float(start_dist),
            sec_length=float(np.sum(segment_lengths)),
            xstart=starts[:, 0].tolist(),
            xend=ends[:, 0].tolist(),
            xcenter=midpoints[:, 0].tolist(),
            xdirection=directions[:, 0].tolist(),
            ystart=starts[:, 1].tolist(),
            yend=ends[:, 1].tolist(),
            ycenter=midpoints[:, 1].tolist(),
            ydirection=directions[:, 1].tolist(),
            zstart=starts[:, 2].tolist(),
            zend=ends[:, 2].tolist(),
            zcenter=midpoints[:, 2].tolist(),
            zdirection=directions[:, 2].tolist(),
            diam=diameters[:-1].tolist(),
            length=segment_lengths.tolist(),
            distance=seg_distances.tolist(),
            segment_distance_from_soma=seg_distances.tolist(),
            segx=np.linspace(0, 1, num_segments).tolist(),
            neuron_section_id=section.id,
            neuron_segments_offset=[0] * num_segments,
        )

    # 1. Soma Processing
    soma = morphology.soma
    if len(soma.points) > 0:
        points = soma.points
        diameters = soma.diameters

        # Handle single-point vs multi-point somas
        if len(points) == 1:
            starts = points
            ends = points
            midpoints = points
            directions = np.zeros_like(points)
            segment_lengths = np.array([0.0])
            diam_list = diameters.tolist()
        else:
            starts = points[:-1]
            ends = points[1:]
            directions = ends - starts
            segment_lengths = np.linalg.norm(directions, axis=1)
            midpoints = (starts + ends) / 2.0
            diam_list = diameters[:-1].tolist()

        num_segments = len(segment_lengths)
        cumulative_internal_lengths = np.cumsum(segment_lengths)
        seg_distances = np.insert(cumulative_internal_lengths[:-1], 0, 0)

        morphology_data["soma[0]"] = NeuronSectionInfo(
            index=-1,
            parent_index=-1,
            name="soma[0]",
            nseg=num_segments,
            distance_from_soma=0.0,
            sec_length=float(np.sum(segment_lengths)),
            xstart=starts[:, 0].tolist(),
            xend=ends[:, 0].tolist(),
            xcenter=midpoints[:, 0].tolist(),
            xdirection=directions[:, 0].tolist(),
            ystart=starts[:, 1].tolist(),
            yend=ends[:, 1].tolist(),
            ycenter=midpoints[:, 1].tolist(),
            ydirection=directions[:, 1].tolist(),
            zstart=starts[:, 2].tolist(),
            zend=ends[:, 2].tolist(),
            zcenter=midpoints[:, 2].tolist(),
            zdirection=directions[:, 2].tolist(),
            diam=diam_list,
            length=segment_lengths.tolist(),
            distance=seg_distances.tolist(),
            segment_distance_from_soma=seg_distances.tolist(),
            segx=np.linspace(0, 1, num_segments).tolist() if num_segments > 1 else [0.5],
            neuron_section_id=-1,
            neuron_segments_offset=[0] * num_segments,
        )

    return morphology_data

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
from app.schemas.circuit_visualization import (
    MorphoViewerTreeItemType,
    MorphPath,
    Node,
    Nodes,
    SectionDict,
)

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

                soma_diameters = morph.soma.diameters
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


def get_morphology_data(morphology: morphio.Morphology) -> list[SectionDict]:
    sections: list[SectionDict] = []

    soma = morphology.soma
    has_soma = soma is not None and len(soma.points) > 0

    if has_soma:
        sections.append(
            {
                "id": "soma",
                "parent_id": None,
                "type": MorphoViewerTreeItemType.Soma,
                "points": soma.points.tolist(),
                "radii": (np.array(soma.diameters) / 2.0).tolist(),
            }
        )

    for section in morphology.iter():
        if section.is_root:  # noqa: SIM108
            parent_id = "soma" if has_soma else None
        else:
            parent_id = str(section.parent.id)

        sections.append(
            {
                "id": str(section.id),
                "parent_id": parent_id,
                "type": _map_section_type(section.type),
                "points": section.points.tolist(),
                "radii": (np.array(section.diameters) / 2.0).tolist(),
            }
        )

    return sections

import tempfile
import urllib.parse
from http import HTTPStatus
from pathlib import Path
from typing import Annotated, TypedDict, cast
from uuid import UUID

import entitysdk.client
import entitysdk.exception
import h5py
import morphio
import numpy as np
from bluepysnap import Circuit as CircuitConfig
from bluepysnap.exceptions import BluepySnapError
from entitysdk.client import Client
from entitysdk.models import Circuit
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.errors import ApiErrorCode
from app.logger import L

router = APIRouter(
    prefix="/circuit/viz", tags=["visualization"], dependencies=[Depends(user_verified)]
)


PositionVector = Annotated[tuple[float, float, float], "x", "y", "z"]
OrientationVector = Annotated[tuple[float, float, float, float], "x", "y", "z", "w"]


class Node(TypedDict):
    morphology_path: str  # Path to the morphology in the circuit's sonata directory
    position: PositionVector
    orientation: OrientationVector
    soma_radius: float


Nodes = list[Node]


class NeuronSectionInfo(TypedDict):
    index: int
    name: str
    nseg: int
    distance_from_soma: float
    sec_length: float
    xstart: list[float]
    xend: list[float]
    xcenter: list[float]
    xdirection: list[float]
    ystart: list[float]
    yend: list[float]
    ycenter: list[float]
    ydirection: list[float]
    zstart: list[float]
    zend: list[float]
    zcenter: list[float]
    zdirection: list[float]
    diam: list[float]
    length: list[float]
    distance: list[float]
    segment_distance_from_soma: list[float]
    segx: list[float]
    neuron_section_id: int
    neuron_segments_offset: list[int]


MorphologyDict = dict[str, NeuronSectionInfo]


@router.get(
    "/{circuit_id}/nodes",
    summary="Circuit nodes",
    description="Returns a list of nodes for visualization",
)
def circuit_nodes(
    circuit_id: UUID,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> Nodes:
    asset_id = circuit_asset_id(db_client, circuit_id)

    with tempfile.TemporaryDirectory() as temp_dir:
        parent_path = Path(temp_dir).resolve()
        config = download_circuit_config(db_client, circuit_id, asset_id, parent_path)

    return get_nodes(config, parent_path, db_client, circuit_id, asset_id)


@router.get(
    "/{circuit_id}/morphologies/{morphology_path}",
    summary="A morphology from a circuit's sonata directory",
    description="Returns a morphology for visualization",
)
def circuit_morphology(
    circuit_id: UUID,
    morphology_path: str,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> MorphologyDict:
    asset_id = circuit_asset_id(db_client, circuit_id)

    with tempfile.TemporaryDirectory() as temp_dir:
        parent_path = Path(temp_dir).resolve()
        try:
            return get_morphology(
                parent_path,
                db_client,
                circuit_id,
                asset_id,
                Path(urllib.parse.unquote(morphology_path + ".swc")),
            )
        except HTTPException:
            raise
        except Exception as e:
            L.exception(e)
            raise HTTPException(status_code=404, detail="Morphology not found") from e


def get_nodes(
    config: CircuitConfig, parent_path: Path, db_client: Client, circuit_id: UUID, asset_id: UUID
) -> Nodes:
    all_nodes = []
    try:
        for node_network in config.config["networks"]["nodes"]:
            for pop_name, pop_config in node_network["populations"].items():
                if pop_config.get("type") != "biophysical":
                    continue

                nodes_file_path = Path(node_network["nodes_file"])
                asset_path = nodes_file_path.relative_to(parent_path)

                morphologies_dir = (
                    Path(pop_config["morphologies_dir"])
                    if "morphologies_dir" in pop_config
                    else Path(config.config["components"]["morphologies_dir"])
                ).relative_to(parent_path)

                all_nodes += get_population_nodes(
                    pop_name,
                    db_client,
                    circuit_id,
                    asset_id,
                    parent_path,
                    asset_path,
                    morphologies_dir,
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


def circuit_asset_id(client: Client, circuit_id: UUID) -> UUID:
    try:
        circuit = client.get_entity(entity_id=circuit_id, entity_type=Circuit)
    except Exception as e:
        L.exception(e)
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail={
                "code": ApiErrorCode.NOT_FOUND,
                "detail": "Circuit not found",
            },
        ) from e

    if circuit.scale not in {"small", "pair"}:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Circuit's scale should be 'small' or 'pair'",
            },
        )

    asset = next((a for a in circuit.assets if a.label == "sonata_circuit"), None)

    if asset is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Circuit is missing a sonata_circuit asset",
            },
        )

    return asset.id


def download_circuit_config(
    client: Client, circuit_id: UUID, asset_id: UUID, directory: Path
) -> CircuitConfig:
    circuit_config = Path("circuit_config.json")

    try:
        file_path = directory / circuit_config

        client.download_file(
            entity_id=circuit_id,
            entity_type=Circuit,
            asset_id=asset_id,
            output_path=file_path,
            asset_path=circuit_config,
        )

        return CircuitConfig(file_path)

    except BluepySnapError as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Invalid circuit configuration",
            },
        ) from e

    except Exception as e:
        L.exception(e)
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Circuit is missing a circuit_config.json asset",
            },
        ) from e


def get_population_nodes(
    population_name: str,
    db_client: Client,
    circuit_id: UUID,
    asset_id: UUID,
    parent_dir: Path,
    asset_path: Path,
    morphologies_dir: Path,
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
        with h5py.File(nodes_file_path, "r") as f:
            path = f"nodes/{population_name}/0"
            pop_group = f[path]

            assert isinstance(pop_group, h5py.Group), f"Path {path} is not a Group"  # noqa: S101
            x = get_group(pop_group, "x")
            y = get_group(pop_group, "y")
            z = get_group(pop_group, "z")
            qx = get_group(pop_group, "orientation_x")
            qy = get_group(pop_group, "orientation_y")
            qz = get_group(pop_group, "orientation_z")
            qw = get_group(pop_group, "orientation_w")

            morph_raw = get_group(pop_group, "morphology")
            morph_files = [m.decode("utf-8") for m in morph_raw if isinstance(m, bytes)]

            def morph_path(i: int) -> Path:
                return morphologies_dir / (morph_files[i] + ".swc")

            radii = []

            for i in range(len(x)):
                try:
                    radii.append(
                        get_soma_radius(parent_dir, db_client, circuit_id, asset_id, morph_path(i))
                    )
                except RuntimeError:
                    L.warning(f"Couldn't get morphology {morph_path(i)} for {circuit_id}")
                    radii.append(None)

            return [
                Node(
                    position=cast("PositionVector", tuple(map(float, [x[i], y[i], z[i]]))),
                    orientation=cast(
                        "OrientationVector", tuple(map(float, [qx[i], qy[i], qz[i], qw[i]]))
                    ),
                    morphology_path=str(morphologies_dir / morph_files[i]),
                    soma_radius=radii[i],
                )
                for i in range(len(x))
            ]

    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": f"Couldn't get nodes from population {population_name}",
            },
        ) from e


def get_group(group: h5py.Group | h5py.Dataset | h5py.Datatype, key: str) -> np.ndarray:
    if not isinstance(group, h5py.Group):
        msg = "Expected a Group"
        raise TypeError(msg)

    child_group = group[key]

    if not isinstance(child_group, (h5py.Group, h5py.Dataset)):
        msg = "Expected a Group or Dataset"
        raise TypeError(msg)

    res = child_group[:]

    if not isinstance(res, np.ndarray):
        msg = "Expected the dataset to be an array"
        raise TypeError(msg)

    return res


def get_morphology(
    parent_dir: Path, client: Client, circuit_id: UUID, asset_id: UUID, morph_path: Path
) -> MorphologyDict:
    parent_dir = parent_dir.resolve()
    output_path = (parent_dir / morph_path).resolve()

    if not output_path.relative_to(parent_dir):
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
        return get_morphology_data(str(output_path))
    except Exception as e:
        msg = f"Could not parse morphology {morph_path}"
        raise HTTPException(status_code=500, detail=msg) from e


def get_soma_radius(
    parent_dir: Path,
    client: Client,
    circuit_id: UUID,
    asset_id: UUID,
    morph_path: Path,
) -> float:
    try:
        L.info(f"Downloading morphology {morph_path}")

        output_path = parent_dir / morph_path

        if not output_path.exists():
            client.download_file(
                entity_type=Circuit,
                output_path=output_path,
                entity_id=circuit_id,
                asset_id=asset_id,
                asset_path=morph_path,
            )

        morph = morphio.Morphology(output_path)
        soma_diameters = morph.soma.diameters

        if len(soma_diameters) == 0:
            return 0.0

        return float(np.mean(soma_diameters) / 2.0)

    except Exception as e:
        msg = f"Could not get morphology's {morph_path} soma radius from circuit {circuit_id}"
        raise RuntimeError(msg) from e


def get_morphology_data(swc_path: str) -> MorphologyDict:
    """Parses an SWC file into a segment-based dictionary optimized for visualization."""
    morphology = morphio.Morphology(swc_path)

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

    morphology_data: MorphologyDict = {}

    for section in morphology.sections:
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

        section_key = f"section_{section.id}"
        num_segments = len(segment_lengths)

        morphology_data[section_key] = {
            "index": section.id,
            "name": section_key,
            "nseg": num_segments,
            "distance_from_soma": float(start_dist),
            "sec_length": float(np.sum(segment_lengths)),
            "xstart": starts[:, 0].tolist(),
            "xend": ends[:, 0].tolist(),
            "xcenter": midpoints[:, 0].tolist(),
            "xdirection": directions[:, 0].tolist(),
            "ystart": starts[:, 1].tolist(),
            "yend": ends[:, 1].tolist(),
            "ycenter": midpoints[:, 1].tolist(),
            "ydirection": directions[:, 1].tolist(),
            "zstart": starts[:, 2].tolist(),
            "zend": ends[:, 2].tolist(),
            "zcenter": midpoints[:, 2].tolist(),
            "zdirection": directions[:, 2].tolist(),
            "diam": diameters[:-1].tolist(),
            "length": segment_lengths.tolist(),
            "distance": seg_distances.tolist(),
            "segment_distance_from_soma": seg_distances.tolist(),
            "segx": np.linspace(0, 1, num_segments).tolist(),
            "neuron_section_id": section.id,
            "neuron_segments_offset": [0] * num_segments,
        }

    return morphology_data

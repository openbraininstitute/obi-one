"""SONATA artifact generation for Build Synaptome."""

# ruff: noqa: EM101, EM102, TRY003, TRY301

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import bluepysnap
import morphio
import numpy as np
import pandas as pd
from bluepysnap.nodes import NodePopulation

from obi_one.scientific.blocks.morphology_locations.base import MorphologyLocationsBlock
from obi_one.scientific.blocks.synaptic_models.base import SynapticModelBase
from obi_one.scientific.library.map_em_synapses.write_sonata_edge_file import write_edges
from obi_one.scientific.library.map_em_synapses.write_sonata_nodes_file import write_virtual_nodes
from obi_one.scientific.library.morphology_locations import (
    _PRE_IDX,
    _SEC_ID,
    _SEC_LOC,
    _SEC_TYP,
    _SEG_ID,
    _SEG_OFF,
)

if TYPE_CHECKING:
    from entitysdk import Client

    from obi_one.scientific.tasks.build_synaptome import BuildSynaptomeSingleConfig

_SOURCE_ID = "pre_node_id"
_TARGET_ID = "post_node_id"


@dataclass(frozen=True)
class BuildSynaptomeResult:
    """Files produced by a Build Synaptome build."""

    circuit_config_path: Path
    output_directory: Path
    generated_files: tuple[Path, ...]


class BuildSynaptomeError(ValueError):
    """Raised when a Build Synaptome artifact cannot be generated or validated."""


@contextmanager
def _preserve_numpy_random_state() -> Iterator[None]:
    """Isolate legacy morphology placers that use NumPy's global RNG."""
    state = np.random.get_state()  # noqa: NPY002 - called placer uses the legacy global RNG
    try:
        yield
    finally:
        np.random.set_state(state)  # noqa: NPY002 - restore legacy global RNG state


def _safe_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    return name or "group"


def _target_population(circuit: bluepysnap.Circuit) -> tuple[str, NodePopulation]:
    populations = [
        name for name in circuit.nodes.population_names if circuit.nodes[name].type == "biophysical"
    ]
    if len(populations) != 1:
        msg = f"Expected exactly one biophysical target population, found {populations}."
        raise BuildSynaptomeError(msg)
    population = circuit.nodes[populations[0]]
    if population.size != 1:
        msg = f"Expected exactly one target neuron, found {population.size}."
        raise BuildSynaptomeError(msg)
    return populations[0], population


def _generate_locations(
    morphology: morphio.Morphology,
    placement: MorphologyLocationsBlock,
    *,
    group_name: str,
) -> pd.DataFrame:
    count = placement.number_of_locations
    if not isinstance(count, int) or count <= 0:
        raise BuildSynaptomeError(
            f"Synapse group '{group_name}' has invalid location count {count!r}."
        )
    try:
        with _preserve_numpy_random_state():
            locations = placement.points_on(morphology)
    except Exception as exc:
        msg = (
            f"Synapse group '{group_name}' could not generate locations using "
            f"{type(placement).__name__}: {exc}"
        )
        raise BuildSynaptomeError(msg) from exc
    if len(locations) != count:
        msg = (
            f"Synapse group '{group_name}' generated {len(locations)} locations, expected {count}."
        )
        raise BuildSynaptomeError(msg)
    return locations.reset_index(drop=True)


def _location_edge_properties(
    morphology: morphio.Morphology, locations: pd.DataFrame
) -> pd.DataFrame:
    rows: list[dict[str, float | int]] = []
    for location in locations.to_dict(orient="records"):
        section_id = int(location[_SEC_ID])
        segment_id = int(location[_SEG_ID])
        physical_offset = float(location[_SEG_OFF])
        try:
            section = morphology.sections[section_id - 1]
            start = section.points[segment_id, :3].astype(float)
            end = section.points[segment_id + 1, :3].astype(float)
        except (IndexError, KeyError) as exc:
            msg = f"Invalid morphology location section={section_id}, segment={segment_id}."
            raise BuildSynaptomeError(msg) from exc
        segment_length = float(np.linalg.norm(end - start))
        if segment_length <= 0:
            raise BuildSynaptomeError(
                f"Morphology location section={section_id}, segment={segment_id} has zero length."
            )
        segment_offset = physical_offset / segment_length
        if not 0.0 <= segment_offset <= 1.0:
            raise BuildSynaptomeError(
                f"Morphology location section={section_id}, segment={segment_id} has invalid "
                f"normalized offset {segment_offset}."
            )
        center = start + segment_offset * (end - start)
        rows.append(
            {
                "afferent_section_id": section_id,
                "afferent_segment_id": segment_id,
                "afferent_segment_offset": segment_offset,
                "afferent_section_pos": float(location[_SEC_LOC]),
                "afferent_section_type": int(location[_SEC_TYP]),
                "afferent_center_x": center[0],
                "afferent_center_y": center[1],
                "afferent_center_z": center[2],
            }
        )
    return pd.DataFrame(rows)


def _sample_physiology(
    model: SynapticModelBase, indices: pd.DataFrame, *, group_name: str
) -> pd.DataFrame:
    count = len(indices)
    try:
        physiology = model.sample(indices)
    except Exception as exc:
        msg = (
            f"Synapse group '{group_name}' could not sample physiology from "
            f"{type(model).__name__}: {exc}"
        )
        raise BuildSynaptomeError(msg) from exc
    missing = set(model.parameter_names()).difference(physiology.columns)
    if missing or len(physiology) != count:
        msg = (
            f"Synapse group '{group_name}' produced invalid physiology data; "
            f"missing={sorted(missing)}, rows={len(physiology)}, expected={count}."
        )
        raise BuildSynaptomeError(msg)
    return physiology.reset_index(drop=True)


def _append_population_config(
    circuit_config: dict,
    *,
    nodes_file: Path,
    node_population: str,
    edges_file: Path,
    edge_population: str,
) -> None:
    circuit_config["networks"]["nodes"].append(
        {
            "nodes_file": f"$BASE_DIR/{nodes_file.as_posix()}",
            "populations": {node_population: {"type": "virtual"}},
        }
    )
    circuit_config["networks"]["edges"].append(
        {
            "edges_file": f"$BASE_DIR/{edges_file.as_posix()}",
            "populations": {edge_population: {"type": "chemical"}},
        }
    )


def validate_synaptome_artifact(
    circuit_config_path: Path,
    *,
    target_population: str,
    expected_groups: dict[str, tuple[int, int]],
) -> None:
    """Load the artifact through BluePySnap and validate generated references/properties."""
    try:
        circuit = bluepysnap.Circuit(circuit_config_path)
        if circuit.nodes[target_population].size != 1:
            raise BuildSynaptomeError("Generated circuit does not contain exactly one target cell.")
        required = {
            "afferent_section_id",
            "afferent_segment_id",
            "afferent_segment_offset",
            "afferent_section_pos",
            "syn_type_id",
            "conductance",
            "delay",
        }
        for edge_population, (expected_count, expected_sources) in expected_groups.items():
            edges = circuit.edges[edge_population]
            if edges.size != expected_count:
                raise BuildSynaptomeError(
                    f"Edge population '{edge_population}' contains {edges.size} edges, "
                    f"expected {expected_count}."
                )
            missing = required.difference(edges.property_names)
            if missing:
                raise BuildSynaptomeError(
                    f"Edge population '{edge_population}' is missing {sorted(missing)}."
                )
            refs = edges.get(edges.ids(), properties=["@source_node", "@target_node"])
            if not (refs["@target_node"] == 0).all():
                raise BuildSynaptomeError(
                    f"Edge population '{edge_population}' has invalid target node references."
                )
            source_ids = refs["@source_node"].to_numpy()
            if source_ids.min() < 0 or source_ids.max() >= expected_sources:
                raise BuildSynaptomeError(
                    f"Edge population '{edge_population}' has invalid source node references."
                )
            if edges.source.size != expected_sources or edges.target.name != target_population:
                raise BuildSynaptomeError(
                    f"Edge population '{edge_population}' references invalid node populations."
                )
            edges.get(edges.ids(), properties=sorted(required))
    except BuildSynaptomeError:
        raise
    except Exception as exc:
        raise BuildSynaptomeError(f"Generated SONATA circuit failed validation: {exc}") from exc


def build_synaptome_artifact(  # noqa: C901, PLR0914, PLR0915
    config: "BuildSynaptomeSingleConfig",
    output_directory: Path,
    *,
    db_client: "Client",
) -> BuildSynaptomeResult:
    """Stage an ME-model circuit and add generated virtual afferent populations."""
    output_directory = Path(output_directory).resolve()
    if output_directory.exists():
        msg = f"Build Synaptome output directory already exists: '{output_directory}'."
        raise FileExistsError(msg)
    if db_client is None:
        raise BuildSynaptomeError("Build Synaptome requires a db_client to resolve the ME-model.")
    try:
        morphology = config.initialize.me_model.morphio_morphology(db_client)
    except Exception as exc:
        msg = f"Unable to load morphology for ME-model '{config.initialize.me_model.id_str}': {exc}"
        raise BuildSynaptomeError(msg) from exc
    try:
        staged = config.initialize.me_model.stage_circuit(
            db_client=db_client, dest_dir=output_directory, entity_cache=False
        )
    except Exception as exc:
        msg = f"Unable to resolve or stage ME-model '{config.initialize.me_model.id_str}': {exc}"
        raise BuildSynaptomeError(msg) from exc

    circuit_config_path = Path(staged.path).resolve()
    try:
        circuit = bluepysnap.Circuit(circuit_config_path)
        target_name, _ = _target_population(circuit)
        circuit_config = json.loads(circuit_config_path.read_text())
        if circuit.edges.population_names:
            raise BuildSynaptomeError(
                "The staged ME-model circuit already contains edges; Build Synaptome requires "
                "an unconnected single-cell ME-model."
            )

        expected_groups: dict[str, tuple[int, int]] = {}
        used_names: set[str] = set(circuit.nodes.population_names)
        for group_index, (group_key, group) in enumerate(config.synapse_groups.items()):
            base = _safe_name(group_key)
            source_population = f"synaptome_{base}_sources"
            edge_population = f"synaptome_{base}__{_safe_name(target_name)}__chemical"
            if source_population in used_names or edge_population in expected_groups:
                raise BuildSynaptomeError(
                    f"Synapse group '{group_key}' produces a duplicate SONATA population name."
                )
            used_names.add(source_population)

            locations = _generate_locations(
                morphology, group.placement_strategy, group_name=group_key
            )
            count = len(locations)
            source_ids = locations[_PRE_IDX].to_numpy(dtype=np.int64)
            source_count = int(source_ids.max()) + 1
            source_target = pd.DataFrame(
                {_SOURCE_ID: source_ids, _TARGET_ID: np.zeros(count, dtype=np.int64)}
            )
            try:
                synaptic_model = group.synaptic_model.block
            except Exception as exc:
                raise BuildSynaptomeError(
                    f"Synapse group '{group_key}' has an unresolved synaptic model: {exc}"
                ) from exc
            if not isinstance(synaptic_model, SynapticModelBase):
                raise BuildSynaptomeError(
                    f"Synapse group '{group_key}' uses unsupported physiology model "
                    f"{type(synaptic_model).__name__}."
                )

            edge_data = pd.concat(
                [
                    _location_edge_properties(morphology, locations),
                    _sample_physiology(synaptic_model, source_target, group_name=group_key),
                ],
                axis=1,
            )
            edge_data["afferent_group_id"] = np.full(count, group_index, dtype=np.int32)
            group_dir = Path("synaptome") / base
            nodes_relative = group_dir / "nodes.h5"
            edges_relative = group_dir / "edges.h5"
            write_virtual_nodes(output_directory / nodes_relative, source_population, source_count)
            write_edges(
                output_directory / edges_relative,
                edge_population,
                source_target,
                edge_data,
                source_population,
                target_name,
                n_src=source_count,
                n_tgt=1,
            )
            _append_population_config(
                circuit_config,
                nodes_file=nodes_relative,
                node_population=source_population,
                edges_file=edges_relative,
                edge_population=edge_population,
            )
            expected_groups[edge_population] = (count, source_count)

        circuit_config_path.write_text(json.dumps(circuit_config, indent=2) + "\n")
        validate_synaptome_artifact(
            circuit_config_path,
            target_population=target_name,
            expected_groups=expected_groups,
        )
    except BuildSynaptomeError:
        raise
    except Exception as exc:
        raise BuildSynaptomeError(f"Failed to write a valid SONATA artifact: {exc}") from exc

    generated_files = tuple(sorted(path for path in output_directory.rglob("*") if path.is_file()))
    return BuildSynaptomeResult(
        circuit_config_path=circuit_config_path,
        output_directory=output_directory,
        generated_files=generated_files,
    )

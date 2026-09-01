"""Helpers for validating brainbuilder id_mapping.json in SONATA circuits."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import libsonata

if TYPE_CHECKING:
    from pathlib import Path

    from bluepysnap import Circuit as SnapCircuitType

L = logging.getLogger(__name__)


def get_population_sizes(circuit: SnapCircuitType) -> dict[str, int]:
    """Return per-population node counts via bluepysnap ``population.size``."""
    pop_sizes: dict[str, int] = {}
    for pop_name in circuit.nodes.population_names:
        try:
            pop_sizes[pop_name] = int(circuit.nodes[pop_name].size)
        except Exception as e:  # ruff: ignore[blind-except]
            L.warning("Could not read size for population '%s': %s", pop_name, e)
    return pop_sizes


def find_stale_populations(mapping: dict, pop_sizes: dict[str, int]) -> list[str]:
    """Identify populations where id_mapping new_id exceeds the population size."""
    stale: list[str] = []
    for pop_name, entry in mapping.items():
        if not isinstance(entry, dict) or "new_id" not in entry:
            continue
        new_ids = entry["new_id"]
        if not new_ids:
            continue
        max_new_id = max(new_ids)
        pop_size = pop_sizes.get(pop_name)
        if pop_size is not None and max_new_id >= pop_size:
            stale.append(
                f"'{pop_name}': max new_id={max_new_id} but population has {pop_size} nodes"
            )
    return stale


def validate_id_mapping_files(circuit_config_path: Path, circuit: SnapCircuitType) -> list[str]:
    """Validate the brainbuilder id_mapping.json if present.

    id_mapping.json is produced by brainbuilder's subcircuit extraction and referenced at
    components.provenance.id_mapping in circuit_config.json. Its format per population is:
        { "new_id": [...], "parent_id": [...], "original_id": [...],
          "parent_name": "...", "original_name": "..." }

    When nodes are replaced (different count or IDs), the new_id values may exceed the
    population size and the mapping becomes invalid. We warn and remove the stale file.

    Returns a list of warning messages.
    """
    config = libsonata.CircuitConfig.from_file(str(circuit_config_path))
    cfg = json.loads(config.expanded_json)

    id_mapping_rel = cfg.get("components", {}).get("provenance", {}).get("id_mapping")
    if not id_mapping_rel:
        return []

    id_mapping_path = circuit_config_path.parent / id_mapping_rel
    if not id_mapping_path.exists():
        return []

    try:
        mapping: dict = json.loads(id_mapping_path.read_text())
    except Exception as e:  # ruff: ignore[blind-except]
        return [f"id_mapping.json: could not parse: {e}"]

    pop_sizes = get_population_sizes(circuit)
    stale_populations = find_stale_populations(mapping, pop_sizes)

    if not stale_populations:
        return []

    detail = "; ".join(stale_populations)
    id_mapping_path.unlink()
    msg = (
        f"id_mapping.json is stale after nodes replacement ({detail}) — "
        "file removed from the circuit (regenerate with brainbuilder if needed)"
    )
    L.warning(msg)
    return [msg]

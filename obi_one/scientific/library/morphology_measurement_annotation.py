"""NeuroM-based morphology measurement annotation helpers."""

import copy
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import neurom as nm
import numpy as np
from neurom.core import Morphology
from neurom.core.morphology import Section

L = logging.getLogger(__name__)

DEFAULT_NEURITE_DOMAIN = "basal_dendrite"
TARGET_NEURITE_DOMAINS = ("apical_dendrite", "axon")

MIN_MEASUREMENT_ITEM_ENTRIES = 2
EMPTY_NAME_SET = {None, ""}
AGGREGATE_ITEM_NAMES = {"minimum", "maximum", "median", "mean", "standard_deviation"}
# Profiling on the morphometrics outliers showed these three path-length metrics
# dominate the endpoint runtime. Keep this cache intentionally narrow; other
# NeuroM metrics continue to use nm.get directly.
CACHED_PATH_LENGTH_SECTION_METRICS = {
    "section_path_distances": ("sections", "path_lengths"),
    "terminal_path_lengths": ("leaves", "path_lengths"),
}
CACHED_PATH_LENGTH_METRICS = {
    *CACHED_PATH_LENGTH_SECTION_METRICS,
    "partition_asymmetry_length",
}

_TEMPLATE_PATH = Path(__file__).with_name("morphology_template.json")
_CACHE_MISS = object()


@dataclass(frozen=True)
class _NeuritePathLengthCache:
    """Cached values for the three profiled path-length bottleneck metrics."""

    sections: list[Any]
    leaves: list[Any]
    bifurcations: list[Any]
    path_lengths: dict[Any, Any]
    subtree_lengths: dict[Any, Any]
    total_length: Any


@cache
def get_morphology_template() -> dict:
    """Return the cached morphology measurement annotation JSON template."""
    return json.loads(_TEMPLATE_PATH.read_text())


@cache
def get_morphology_analysis_dict() -> dict[str, list[list[str]]]:
    """Return the cached analysis dictionary derived from the morphology template."""
    analysis_dict_base = create_analysis_dict(get_morphology_template())
    analysis_dict = dict(analysis_dict_base)

    if DEFAULT_NEURITE_DOMAIN in analysis_dict:
        default_analysis = analysis_dict[DEFAULT_NEURITE_DOMAIN]
        for domain in TARGET_NEURITE_DOMAINS:
            analysis_dict.setdefault(domain, default_analysis)

    return analysis_dict


def _update_entity_id_recursive(obj: dict | list, entity_id: str) -> None:
    """Recursively update any 'entity_id' key to the given entity_id."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key == "entity_id":
                obj[key] = entity_id
            else:
                _update_entity_id_recursive(val, entity_id)
    elif isinstance(obj, list):
        for item in obj:
            _update_entity_id_recursive(item, entity_id)


def find_pref_labels_by_domain(
    value: dict | list,
    results: defaultdict[str, list[list[str]]],
) -> None:
    """Recursively search for pref_label and structural_domain in nested JSON."""
    if isinstance(value, dict):
        if "pref_label" in value and "structural_domain" in value:
            try:
                domain = value["structural_domain"]
                label = value["pref_label"]
                units = value["measurement_items"][0]["unit"]
                results[domain].append([label, units])
            except (KeyError, IndexError):
                pass
        for v in value.values():
            find_pref_labels_by_domain(v, results)

    elif isinstance(value, list):
        for item in value:
            find_pref_labels_by_domain(item, results)


def create_analysis_dict(
    obj: dict | list,
    results: defaultdict[str, list[list[str]]] | None = None,
) -> defaultdict[str, list[list[str]]]:
    """Recursively collect pref_labels and units grouped by structural_domain."""
    if results is None:
        results = defaultdict(list)

    if isinstance(obj, dict):
        if "pref_label" in obj and "structural_domain" in obj:
            try:
                domain = obj["structural_domain"]
                label = obj["pref_label"]
                unit = obj["measurement_items"][0]["unit"]
                results[domain].append([label, unit])
            except (KeyError, IndexError):
                pass
        for value in obj.values():
            create_analysis_dict(value, results)

    elif isinstance(obj, list):
        for item in obj:
            create_analysis_dict(item, results)

    return results


def _matching_neurites(neuron: Morphology, neurite_type: Any | None) -> list[Any]:
    """Return neurites matching NeuroM's simple morphology-level neurite filter."""
    if neurite_type is None:
        return list(neuron.neurites)

    return [neurite for neurite in neuron.neurites if neurite.type == neurite_type]


def _build_neurite_path_length_cache(neurite: Any) -> _NeuritePathLengthCache:
    """Precompute only the path lengths needed by the profiled slow metrics."""
    sections = list(Section.ipreorder(neurite.root_node))
    leaves = list(Section.ileaf(neurite.root_node))
    bifurcations = list(Section.ibifurcation_point(neurite.root_node))

    path_lengths: dict[Any, Any] = {}

    def _walk_upstream_values(section: Any, path_before_s: Any) -> None:
        path_lengths[section] = path_before_s + section.length
        for child in section.children:
            _walk_upstream_values(child, path_lengths[section])

    _walk_upstream_values(neurite.root_node, 0)

    subtree_lengths: dict[Any, Any] = {}

    for section in reversed(sections):
        subtree_lengths[section] = section.length + sum(
            subtree_lengths[child] for child in section.children
        )

    return _NeuritePathLengthCache(
        sections=sections,
        leaves=leaves,
        bifurcations=bifurcations,
        path_lengths=path_lengths,
        subtree_lengths=subtree_lengths,
        total_length=sum(section.length for section in sections),
    )


def _path_length_cache_for_neurite_type(
    neuron: Morphology,
    neurite_type: Any | None,
    path_length_cache: dict[Any, list[_NeuritePathLengthCache]],
) -> list[_NeuritePathLengthCache] | None:
    """Return per-neurite path-length caches, or None to keep NeuroM fallback behavior."""
    cache_key = neurite_type
    if cache_key in path_length_cache:
        return path_length_cache[cache_key]

    neurites = _matching_neurites(neuron, neurite_type)
    if any(neurite.process_subtrees for neurite in neurites):
        return None

    path_length_caches = [_build_neurite_path_length_cache(neurite) for neurite in neurites]
    path_length_cache[cache_key] = path_length_caches
    return path_length_caches


def _partition_asymmetry_length_from_cache(
    cache_entry: _NeuritePathLengthCache,
    bifurcation: Any,
) -> float:
    left, right = bifurcation.children[:2]
    return (
        abs(
            cache_entry.subtree_lengths[left]
            - cache_entry.subtree_lengths[right]
        )
        / cache_entry.total_length
    )


def _cached_path_length_measurement(
    label: str,
    neuron: Morphology,
    neurite_type: Any | None,
    path_length_cache: dict[Any, list[_NeuritePathLengthCache]] | None,
) -> Any:
    """Return cached equivalents for the three profiled path-length bottlenecks."""
    if path_length_cache is None or label not in CACHED_PATH_LENGTH_METRICS:
        return _CACHE_MISS

    path_length_caches = _path_length_cache_for_neurite_type(
        neuron,
        neurite_type,
        path_length_cache,
    )
    if path_length_caches is None:
        return _CACHE_MISS

    if section_value_measurement := CACHED_PATH_LENGTH_SECTION_METRICS.get(label):
        section_attr, value_attr = section_value_measurement
        return [
            getattr(cache_entry, value_attr)[section]
            for cache_entry in path_length_caches
            for section in getattr(cache_entry, section_attr)
        ]

    if label == "partition_asymmetry_length":
        return [
            _partition_asymmetry_length_from_cache(cache_entry, bifurcation)
            for cache_entry in path_length_caches
            for bifurcation in cache_entry.bifurcations
        ]

    return _CACHE_MISS


def _process_measurement(
    label: str,
    unit: str,
    neuron: Morphology,
    neurite_type: int | None = None,
    path_length_cache: dict[Any, list[_NeuritePathLengthCache]] | None = None,
) -> list[Any]:
    """Get a neurom measurement, aggregate if it's a list, and package the result."""
    nm_get_key = "max_radial_distance" if label.endswith("max_radial_distance") else label

    data = _cached_path_length_measurement(label, neuron, neurite_type, path_length_cache)

    if data is _CACHE_MISS:
        if neurite_type is not None:
            data = nm.get(nm_get_key, neuron, neurite_type=neurite_type)
        else:
            data = nm.get(nm_get_key, neuron)

    if isinstance(data, list):
        nan_count = sum(
            isinstance(value, (float, np.floating)) and np.isnan(value) for value in data
        )
        if nan_count:
            L.warning(
                "Skipping morphology metric %s because %d of %d values are NaN",
                label,
                nan_count,
                len(data),
            )
            data = None
    elif isinstance(data, (float, np.floating)) and np.isnan(data):
        L.warning("Skipping NaN value for morphology metric %s", label)
        data = None

    if isinstance(data, list) and not data:
        data = None
    elements = [label, data, unit]

    if isinstance(data, list) and data:
        try:
            min_val = float(np.min(data))
            max_val = float(np.max(data))
            median_val = float(np.median(data))
            mean_val = float(np.mean(data))
            std_val = float(np.std(data))

            new_data = [
                ["minimum", min_val, unit],
                ["maximum", max_val, unit],
                ["median", median_val, unit],
                ["mean", mean_val, unit],
                ["standard_deviation", std_val, unit],
            ]
            elements = [label, new_data, unit]
        except ValueError:
            return [label, None, unit]

    return elements


def build_results_dict(
    analysis_dict: dict[str, list[list[str]]],
    neuron: Morphology,
) -> dict[str, list[list[Any]]]:
    """Analyze neuron morphology using neurom based on the analysis_dict structure."""
    path_length_cache: dict[Any, list[_NeuritePathLengthCache]] = {}

    def _run_analysis(category_key: str, neurite_type: int | None = None) -> list[list[Any]]:
        category_results = []
        for label, unit in analysis_dict.get(category_key, []):
            result = _process_measurement(
                label,
                unit,
                neuron,
                neurite_type=neurite_type,
                path_length_cache=path_length_cache,
            )
            category_results.append(result)
        return category_results

    results_dict: dict[str, list[list[Any]]] = {}

    results_dict["soma"] = _run_analysis("soma")
    results_dict["neuron_morphology"] = _run_analysis("neuron_morphology")

    if _has_neurite_type(neuron, nm.AXON):  # ty:ignore[invalid-argument-type]
        results_dict["axon"] = _run_analysis("axon", nm.AXON)  # ty:ignore[invalid-argument-type]
    else:
        results_dict["axon"] = []

    if _has_neurite_type(neuron, nm.BASAL_DENDRITE):  # ty:ignore[invalid-argument-type]
        results_dict["basal_dendrite"] = _run_analysis("basal_dendrite", nm.BASAL_DENDRITE)  # ty:ignore[invalid-argument-type]
    else:
        results_dict["basal_dendrite"] = []

    if _has_neurite_type(neuron, nm.APICAL_DENDRITE):  # ty:ignore[invalid-argument-type]
        results_dict["apical_dendrite"] = _run_analysis("apical_dendrite", nm.APICAL_DENDRITE)  # ty:ignore[invalid-argument-type]
    else:
        results_dict["apical_dendrite"] = []

    return results_dict


def _update_aggregate_items(
    measurement_items: list[dict[str, Any]],
    entry_value: list,
) -> None:
    """Update measurement_items with aggregated (list-of-lists) values."""
    items_by_name = {item.get("name"): item for item in measurement_items if item.get("name")}

    for sub_entry in entry_value:
        if len(sub_entry) < MIN_MEASUREMENT_ITEM_ENTRIES:
            continue
        sub_name = sub_entry[0]
        sub_val = sub_entry[1]
        sub_unit = sub_entry[2] if len(sub_entry) > MIN_MEASUREMENT_ITEM_ENTRIES else None

        if sub_name in items_by_name:
            item = items_by_name[sub_name]
            item["value"] = sub_val
            if sub_unit is not None:
                item["unit"] = sub_unit
        else:
            matched = False
            check_names = EMPTY_NAME_SET | {sub_name}
            for item in measurement_items:
                if item.get("name") in check_names:
                    item["value"] = sub_val
                    if sub_unit is not None:
                        item["unit"] = sub_unit
                    matched = True
                    break
            if not matched:
                new_item: dict[str, str | float | int | None] = {
                    "name": sub_name,
                    "value": sub_val,
                }
                if sub_unit is not None:
                    new_item["unit"] = sub_unit
                measurement_items.append(new_item)


def _update_scalar_items(
    measurement_items: list[dict[str, Any]],
    entry_value: float | list | tuple,
) -> None:
    """Update measurement_items with a scalar value."""
    scalar_val = entry_value
    scalar_unit = None

    if (
        isinstance(entry_value, (list, tuple))
        and len(entry_value) >= MIN_MEASUREMENT_ITEM_ENTRIES
        and not isinstance(entry_value[0], list)
    ):
        scalar_val = entry_value[0]
        scalar_unit = entry_value[1]

    raw_item = next((item for item in measurement_items if item.get("name") == "raw"), None)
    if raw_item is None and measurement_items:
        raw_item = measurement_items[0]

    if raw_item is not None:
        raw_item["value"] = scalar_val
        if scalar_unit is not None:
            raw_item["unit"] = scalar_unit
    else:
        new_item: dict[str, str | float | int | None] = {"name": "raw", "value": scalar_val}  # ty:ignore[invalid-assignment]
        if scalar_unit is not None:
            new_item["unit"] = scalar_unit
        measurement_items.append(new_item)


def update_measurement_items(
    measurement_items: list[dict[str, Any]],
    entry_value: float | list | tuple,
) -> None:
    """Update measurement_items from a scalar or aggregate stats payload."""
    if (
        isinstance(entry_value, list)
        and entry_value
        and all(isinstance(x, list) for x in entry_value)
    ):
        _update_aggregate_items(measurement_items, entry_value)
    else:
        _update_scalar_items(measurement_items, entry_value)


def _get_payload(entry: list[Any]) -> Any | None:
    """Return payload to write, or None if it should be skipped."""
    if not entry or len(entry) <= 1:
        return None

    payload = entry[1]

    if payload is None or (isinstance(payload, list) and not payload):
        return None

    is_complex_list = isinstance(payload, list) and payload and isinstance(payload[0], list)
    if not is_complex_list and len(entry) > MIN_MEASUREMENT_ITEM_ENTRIES:
        payload = (payload, entry[2])

    return payload


def fill_json(
    template: dict[str, Any],
    values: dict[str, Any],
    entity_id: str,
) -> dict[str, Any]:
    """Traverse JSON template and fill measurement values."""
    _update_entity_id_recursive(template, entity_id)

    for data_obj in template.get("data", []):
        for measurement in data_obj.get("measurement_kinds", []):
            domain = measurement.get("structural_domain")
            label = measurement.get("pref_label")
            if not domain or not label:
                continue

            for entry in values.get(domain, []):
                if not entry or entry[0] != label:
                    continue

                payload = _get_payload(entry)
                if payload is None:
                    break

                measurement.setdefault("measurement_items", [])
                update_measurement_items(measurement["measurement_items"], payload)
                break

    return template


def _is_valid_measurement_value(value: Any) -> bool:
    """Return True when a measurement item value should be kept."""
    if value is None:
        return False
    return not (isinstance(value, (float, np.floating)) and not np.isfinite(value))


def _filter_valid_measurement_kinds(
    measurement_kinds: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop measurement kinds containing null/NaN/non-finite aggregate values."""
    valid_measurement_kinds = []

    for measurement_kind in measurement_kinds:
        original_items = measurement_kind.get("measurement_items", [])
        original_item_names = {item.get("name") for item in original_items}

        measurement_items = [
            item for item in original_items if _is_valid_measurement_value(item.get("value"))
        ]
        measurement_item_names = {item.get("name") for item in measurement_items}

        if AGGREGATE_ITEM_NAMES.issubset(original_item_names) and not AGGREGATE_ITEM_NAMES.issubset(
            measurement_item_names
        ):
            continue

        if measurement_items:
            valid_measurement_kinds.append(
                {
                    **measurement_kind,
                    "measurement_items": measurement_items,
                }
            )

    return valid_measurement_kinds


def compute_morphometrics(morphology_path: str | Path) -> list[dict[str, Any]]:
    """Compute morphometric measurements for a morphology file."""
    neuron = nm.load_morphology(str(morphology_path))
    results_dict = build_results_dict(get_morphology_analysis_dict(), neuron)
    filled = fill_json(copy.deepcopy(get_morphology_template()), results_dict, entity_id="temp_id")
    measurement_kinds = filled["data"][0]["measurement_kinds"]
    return _filter_valid_measurement_kinds(measurement_kinds)


def _has_neurite_type(neuron: Morphology, neurite_type: int) -> bool:
    """Return True if the morphology contains at least one neurite of the given type."""
    return any(n.type == neurite_type for n in neuron.neurites)

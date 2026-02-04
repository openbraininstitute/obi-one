from collections import defaultdict
from typing import Any

import neurom as nm
import numpy as np
from neurom.core import Morphology

# Define constants for magic numbers and set literal checks
MIN_MEASUREMENT_ITEM_ENTRIES = 2
EMPTY_NAME_SET = {None, ""}


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
    # NOTE: results now stores list of [label, unit]
    # Changed list[str] to list[list[str]] for clarity
    results: defaultdict[str, list[list[str]]] | None = None,
) -> defaultdict[str, list[list[str]]]:  # Changed list[str] to list[list[str]] for clarity
    """Recursively collect pref_labels and units grouped by structural_domain."""
    if results is None:
        results = defaultdict(list)

    if isinstance(obj, dict):
        if "pref_label" in obj and "structural_domain" in obj:
            try:
                domain = obj["structural_domain"]
                label = obj["pref_label"]
                # Extract the unit from the first item in measurement_items
                unit = obj["measurement_items"][0]["unit"]
                # Append a list [label, unit]
                results[domain].append([label, unit])
            except (KeyError, IndexError):
                # Handle cases where measurement_items or unit might be missing
                pass
        for value in obj.values():
            create_analysis_dict(value, results)

    elif isinstance(obj, list):
        for item in obj:
            create_analysis_dict(item, results)

    return results


def _process_measurement(
    label: str,
    unit: str,
    neuron: Morphology,
    neurite_type: int | None = None,
) -> list[Any]:
    """Helper to get a neurom measurement, aggregate if it's a list, and package the result."""

    nm_get_key = "max_radial_distance" if label.endswith("max_radial_distance") else label

    if neurite_type is not None:
        data = nm.get(nm_get_key, neuron, neurite_type=neurite_type)
    else:
        data = nm.get(nm_get_key, neuron)

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
            new_data = [
                ["minimum", 0, unit],
                ["maximum", 0, unit],
                ["median", 0.0, unit],
                ["mean", 0.0, unit],
                ["standard_deviation", 0.0, unit],
            ]
            elements = [label, new_data, unit]

    return elements


def build_results_dict(
    analysis_dict: dict[str, list[list[str]]],
    neuron: Morphology,
) -> dict[str, list[list[Any]]]:
    """Analyzes neuron morphology using neurom and numpy based on the provided
    analysis_dict structure (which contains [label, unit] pairs).
    """

    def _run_analysis(category_key: str, neurite_type: int | None = None) -> list[list[Any]]:
        category_results = []
        for label, unit in analysis_dict.get(category_key, []):
            result = _process_measurement(label, unit, neuron, neurite_type=neurite_type)
            category_results.append(result)
        return category_results

    results_dict: dict[str, list[list[Any]]] = {}

    results_dict["soma"] = _run_analysis("soma")
    results_dict["neuron_morphology"] = _run_analysis("neuron_morphology")
    results_dict["axon"] = _run_analysis("axon", nm.AXON)
    results_dict["basal_dendrite"] = _run_analysis("basal_dendrite", nm.BASAL_DENDRITE)
    results_dict["apical_dendrite"] = _run_analysis("apical_dendrite", nm.APICAL_DENDRITE)

    return results_dict


def _update_aggregate_items(
    measurement_items: list[dict[str, Any]],
    entry_value: list,
) -> None:
    """Internal helper to update measurement_items with aggregated (list-of-lists) values."""
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
            # Use set literal for checking item names
            check_names = EMPTY_NAME_SET | {sub_name}
            for item in measurement_items:
                if item.get("name") in check_names:
                    item["value"] = sub_val
                    if sub_unit is not None:
                        item["unit"] = sub_unit
                    matched = True
                    break
            if not matched:
                new_item: dict[
                    str,
                    str | float | int | None,
                ] = {"name": sub_name, "value": sub_val}
                if sub_unit is not None:
                    new_item["unit"] = sub_unit
                measurement_items.append(new_item)


def _update_scalar_items(
    measurement_items: list[dict[str, Any]],
    entry_value: float | list | tuple,
) -> None:
    """Internal helper to update measurement_items with a scalar value."""
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
        new_item: dict[str, str | float | int | None] = {"name": "raw", "value": scalar_val}
        if scalar_unit is not None:
            new_item["unit"] = scalar_unit
        measurement_items.append(new_item)


def update_measurement_items(
    measurement_items: list[dict[str, Any]],
    entry_value: float | list | tuple,
) -> None:
    """Measurement_items: list of dicts from JSON (each dict has name, unit, value).
    Entry_value: either a scalar (number) OR a list-of-lists (aggregate stats),
    e.g. 4444.35 OR [['minimum', 4444, 'μm'], ...].
    """
    if (
        isinstance(entry_value, list)
        and entry_value
        and all(isinstance(x, list) for x in entry_value)
    ):
        _update_aggregate_items(measurement_items, entry_value)
    else:
        _update_scalar_items(measurement_items, entry_value)


def fill_json(
    template: dict[str, Any],
    values: dict[str, Any],
    entity_id: str,
) -> dict[str, Any]:
    """Traverse JSON template and fill measurement values.
    Updates any 'entity_id' key (at any depth) to the given entity_id.
    """
    _update_entity_id_recursive(template, entity_id)

    data_list = template.get("data", [])
    for data_obj in data_list:
        measurement_kinds = data_obj.get("measurement_kinds", [])
        for measurement in measurement_kinds:
            domain = measurement.get("structural_domain")
            label = measurement.get("pref_label")
            if not domain or not label:
                continue
            domain_entries = values.get(domain)
            if not domain_entries:
                continue
            for entry in domain_entries:
                if not entry:
                    continue
                entry_label = entry[0]
                if entry_label != label:
                    continue
                payload = entry[1] if len(entry) > 1 else None
                is_complex_list = (
                    isinstance(payload, list) and payload and isinstance(payload[0], list)
                )
                if (
                    payload is not None
                    and not is_complex_list
                    and len(entry) > MIN_MEASUREMENT_ITEM_ENTRIES
                ):
                    payload = (payload, entry[2])
                if "measurement_items" not in measurement:
                    measurement["measurement_items"] = []
                update_measurement_items(measurement["measurement_items"], payload)
                break
    return template

import json
from collections import defaultdict

import uuid
from pathlib import Path

import neurom as nm
from neurom.core.morphology import iter_neurites, iter_sections
import numpy as np

from neurom import view
from neurom.view.matplotlib_utils import (
    update_plot_limits,
)


# Recursive helper function
def find_pref_labels_by_domain(value, results):
    """Recursively search for pref_label and structural_domain in nested JSON."""
    if isinstance(value, dict):
        # If both keys exist, store the pref_label under its structural_domain
        if "pref_label" in value and "structural_domain" in value:
            domain = value["structural_domain"]
            label = value["pref_label"]
            units = value["measurement_items"][0]["unit"]
            results[domain].append([label, units])
        # Recurse deeper
        for v in value.values():
            find_pref_labels_by_domain(v, results)

    elif isinstance(value, list):
        for item in value:
            find_pref_labels_by_domain(item, results)
    

# Function with the analysis
def create_analysis_dict(obj, results=None):
    """Recursively collect pref_labels grouped by structural_domain."""
    if results is None:
        results = defaultdict(list)

    if isinstance(obj, dict):
        # If both keys exist, group pref_label under its domain
        if "pref_label" in obj and "structural_domain" in obj:
            domain = obj["structural_domain"]
            label = obj["pref_label"]
            results[domain].append(label)
        # Recurse into dictionary values
        for value in obj.values():
            find_pref_labels_by_domain(value, results)

    elif isinstance(obj, list):
        # Recurse into each item in list
        for item in obj:
            find_pref_labels_by_domain(item, results)

    return results


def build_results_dict(analysis_dict, neuron):
    results_dict = {}

    #Soma analysis
    soma_analysis = []
    for a in analysis_dict["soma"]:
        b = nm.get(a[0], neuron)
        elements = [a[0], b, a[1]]
        soma_analysis.append(elements)

    #Full morphology analysis
    morphology_analysis = []
    for a in analysis_dict["neuron_morphology"]:
        if a[0] == "morphology_max_radial_distance":
            b = nm.get("max_radial_distance", neuron) 
            #elements = [a[0], b, a[1]]
        else:
            b = nm.get(a[0], neuron)
            #elements = [a[0], b, a[1]]
            if isinstance(b, list): 
                b_new = [["minimum", float(np.min(b)), a[1]], ["maximum", float(np.max(b)), a[1]], ["median", float(np.median(b)), a[1]], ["mean", float(np.mean(b)), a[1]], ["standard_deviation", float(np.std(b)), a[1]]]
                b = b_new
                #elements = [a[0], b, a[1]]
        elements = [a[0], b, a[1]]
        morphology_analysis.append(elements)

    #Axon analysis
    axon_analysis = []
    for a in analysis_dict["axon"]:
        if a[0] == "neurite_max_radial_distance":
            b = nm.get("max_radial_distance", neuron, neurite_type=nm.AXON)
            #elements = [a[0], b, a[1]]
        else:
            b = nm.get(a[0], neuron, neurite_type=nm.AXON)
            #elements = [a[0], b, a[1]]
            if isinstance(b, list): 
                try:
                    b_new = [["minimum", float(np.min(b)), a[1]], ["maximum", float(np.max(b)), a[1]], ["median", float(np.median(b)), a[1]], ["mean", float(np.mean(b)), a[1]], ["standard_deviation", float(np.std(b)), a[1]]]
                    b = b_new
                    #elements = [a[0], b, a[1]]
                except ValueError:
                    b_new = [["minimum", 0, a[1]], ["maximum", 0, a[1]], ["median", 0.0, a[1]], ["mean", 0.0, a[1]], ["standard_deviation", 0.0, a[1]]]
                    b = b_new
                    #elements = [a[0], b, a[1]]
        elements = [a[0], b, a[1]]
        axon_analysis.append(elements)

    #Basal dendrites analysis
    basal_analysis = []
    for a in analysis_dict["basal_dendrite"]:
        if a[0] == "neurite_max_radial_distance":
            b = nm.get("max_radial_distance", neuron, neurite_type=nm.BASAL_DENDRITE)
            elements = [a[0], b, a[1]]
        else:
            b = nm.get(a[0], neuron, neurite_type=nm.BASAL_DENDRITE)
            elements = [a[0], b, a[1]]
            if isinstance(b, list): 
                try:
                    b_new = [["minimum", float(np.min(b)), a[1]], ["maximum", float(np.max(b)), a[1]], ["median", float(np.median(b)), a[1]], ["mean", float(np.mean(b)), a[1]], ["standard_deviation", float(np.std(b)), a[1]]]
                    b = b_new
                except ValueError:
                    b_new = [["minimum", 0, a[1]], ["maximum", 0, a[1]], ["median", 0.0, a[1]], ["mean", 0.0, a[1]], ["standard_deviation", 0.0, a[1]]]
                    b = b_new
                elements = [a[0], b]
        basal_analysis.append(elements)

    #Apical dendrites analysis
    apical_analysis = []
    for a in analysis_dict["apical_dendrite"]:
        if a[0] == "neurite_max_radial_distance":
            b = nm.get("max_radial_distance", neuron, neurite_type=nm.APICAL_DENDRITE)
        else:
            b = nm.get(a[0], neuron, neurite_type=nm.APICAL_DENDRITE)
            if isinstance(b, list): 
                try:
                    b_new = [["minimum", float(np.min(b)), a[1]], ["maximum", float(np.max(b)), a[1]], ["median", float(np.median(b)), a[1]], ["mean", float(np.mean(b)), a[1]], ["standard_deviation", float(np.std(b)), a[1]]]
                    b = b_new
                except ValueError:
                    b_new = [["minimum", 0, a[1]], ["maximum", 0, a[1]], ["median", 0.0, a[1]], ["mean", 0.0, a[1]], ["standard_deviation", 0.0, a[1]]]
                    b = b_new
        elements = [a[0], b, a[1]]
        apical_analysis.append(elements)

    #results_dict["entity_id"] = entity_id
    results_dict["axon"] = axon_analysis
    results_dict["basal_dendrite"] = basal_analysis
    results_dict["apical_dendrite"] = apical_analysis
    results_dict["neuron_morphology"] = morphology_analysis
    results_dict["soma"] = soma_analysis

    return results_dict

def update_measurement_items(measurement_items, entry_value):
    """
    measurement_items: list of dicts from JSON (each dict has name, unit, value)
    entry_value: either a scalar (number) OR a list-of-lists (aggregate stats)
                 e.g. 4444.35  OR  [['minimum', 4444, 'μm'], ...]
    """
    # aggregate case: entry_value is list-of-lists
    if isinstance(entry_value, list) and entry_value and all(isinstance(x, list) for x in entry_value):
        # Build a mapping from name -> item in measurement_items (if names exist)
        items_by_name = {}
        for item in measurement_items:
            name = item.get("name")
            if name:
                items_by_name[name] = item

        # Update each subentry by name match
        for sub in entry_value:
            if len(sub) < 2:
                continue
            sub_name = sub[0]
            sub_val = sub[1]
            sub_unit = sub[2] if len(sub) > 2 else None

            # Prefer updating item with matching 'name'
            if sub_name in items_by_name:
                items_by_name[sub_name]["value"] = sub_val
                if sub_unit is not None:
                    items_by_name[sub_name]["unit"] = sub_unit
            else:
                # If no exact name match, try to update first item that has same unit or fallback: append new item
                matched = False
                for item in measurement_items:
                    # attempt to match by existing unit or missing name
                    if item.get("name") in (None, "", sub_name):
                        item["value"] = sub_val
                        if sub_unit is not None:
                            item["unit"] = sub_unit
                        matched = True
                        break
                if not matched:
                    # append a new item (keeps structure explicit)
                    new_item = {"name": sub_name, "value": sub_val}
                    if sub_unit is not None:
                        new_item["unit"] = sub_unit
                    measurement_items.append(new_item)

    else:
        # scalar case: set first 'raw' item if exists, otherwise first measurement_item
        scalar_val = entry_value
        scalar_unit = None
        # if entry_value is a tuple/list like [value, unit] (rare), handle:
        if isinstance(entry_value, (list, tuple)) and len(entry_value) >= 2 and not isinstance(entry_value[0], list):
            scalar_val = entry_value[0]
            scalar_unit = entry_value[1]

        # find 'raw' item preferentially
        raw_item = None
        for item in measurement_items:
            if item.get("name") == "raw":
                raw_item = item
                break
        if raw_item is None and measurement_items:
            raw_item = measurement_items[0]

        if raw_item is not None:
            raw_item["value"] = scalar_val
            if scalar_unit is not None:
                raw_item["unit"] = scalar_unit
        else:
            # no measurement_items present? create one
            new_item = {"name": "raw", "value": scalar_val}
            if scalar_unit is not None:
                new_item["unit"] = scalar_unit
            measurement_items.append(new_item)

def fill_json(template: dict, values: dict, entity_id: str):
    """
    Traverse JSON template and fill measurement values.
    Updates any 'entity_id' key (at any depth) to the given entity_id.
    """
    # --- update entity_id anywhere in the JSON ---
    def update_entity_id(obj):
        if isinstance(obj, dict):
            for key, val in obj.items():
                if key == "entity_id":
                    obj[key] = entity_id
                else:
                    update_entity_id(val)
        elif isinstance(obj, list):
            for item in obj:
                update_entity_id(item)

    update_entity_id(template)  # updates entity_id at any depth

    # --- now update all measurement values (same logic as before) ---
    data_list = template.get("data", [])
    for data_obj in data_list:
        mk = data_obj.get("measurement_kinds", [])
        for m in mk:
            domain = m.get("structural_domain")
            label = m.get("pref_label")
            if not domain or not label:
                continue
            domain_entries = values.get(domain)
            if not domain_entries:
                continue
            for ent in domain_entries:
                if not ent:
                    continue
                ent_label = ent[0]
                if ent_label != label:
                    continue
                payload = ent[1] if len(ent) > 1 else None
                if payload is not None and not (
                    isinstance(payload, list) and payload and isinstance(payload[0], list)
                ):
                    if len(ent) > 2:
                        payload = (payload, ent[2])
                if "measurement_items" not in m:
                    m["measurement_items"] = []
                update_measurement_items(m["measurement_items"], payload)
                break  # done with this pref_label
    return template


import json
import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import bluepysnap as snap

from obi_one.core.exception import OBIONEError

if TYPE_CHECKING:
    from obi_one.scientific.blocks.neuron_sets.base import NeuronSet
    from obi_one.scientific.library.circuit import Circuit

L = logging.getLogger(__name__)


def add_node_set_to_circuit(
    sonata_circuit: snap.Circuit,
    node_set_dict: dict,
    *,
    overwrite_if_exists: bool = False,
) -> None:
    """Adds the node set definition to a SONATA circuit object to make it accessible
    (in-place).

    Re-adding a name that already maps to an identical definition is allowed: a symbolic
    compound neuron set inlines the definitions of the sets it references, so the same
    generated sub-definition legitimately arrives twice when a referenced set is also
    registered in its own right. Only a genuine redefinition is an error.
    """
    existing_node_sets = sonata_circuit.node_sets.content
    if not overwrite_if_exists:
        for k, v in node_set_dict.items():
            if k in existing_node_sets and existing_node_sets[k] != v:
                msg = f"Node set '{k}' already exists!"
                raise ValueError(msg)
    existing_node_sets.update(node_set_dict)
    sonata_circuit.node_sets = snap.circuit.NodeSets.from_dict(existing_node_sets)


def write_circuit_node_set_file(
    sonata_circuit: snap.Circuit,
    output_path: str,
    file_name: str | None = None,
    *,
    overwrite_if_exists: bool = False,
) -> None:
    """Writes a new node set file of a given SONATA circuit object."""
    L.info("sonata_circuit.node_sets.content: %s", sonata_circuit.node_sets.content)
    if file_name is None:
        # Use circuit's node set file name by default
        file_name = os.path.split(sonata_circuit.config["node_sets_file"])[1]
    else:
        if not isinstance(file_name, str) or len(file_name) == 0:
            msg = "File name must be a non-empty string! Can be omitted to use default file name."
            raise ValueError(msg)
        path = Path(file_name)
        if len(path.stem) == 0 or path.suffix.lower() != ".json":
            msg = "File name must be non-empty and of type .json!"
            raise ValueError(msg)
    Path(output_path).mkdir(parents=True, exist_ok=True)
    output_file = Path(output_path) / file_name

    if not overwrite_if_exists and Path(output_file).exists():
        msg = f"Output file '{output_file}' already exists! Delete or choose to overwrite."
        raise ValueError(msg)

    with Path(output_file).open("w", encoding="utf-8") as f:
        json.dump(sonata_circuit.node_sets.content, f, indent=2)


def write_circuit_compartment_set_file(
    sonata_circuit: snap.Circuit,
    output_path: str,
    compartment_sets: Mapping[str, Any],
    file_name: str | None = None,
    *,
    overwrite_if_exists: bool = False,
) -> Path:
    """Writes a new compartment set file of a given SONATA circuit object."""
    if file_name is None:
        # Use circuit's compartment set file name by default
        file_name = os.path.split(sonata_circuit.config["compartment_sets_file"])[1]
    else:
        if not isinstance(file_name, str) or len(file_name) == 0:
            msg = "File name must be a non-empty string! Can be omitted to use default file name."
            raise ValueError(msg)
        path = Path(file_name)
        if len(path.stem) == 0 or path.suffix.lower() != ".json":
            msg = "File name must be non-empty and of type .json!"
            raise ValueError(msg)
    output_file = Path(output_path) / file_name

    if not overwrite_if_exists and Path(output_file).exists():
        msg = f"Output file '{output_file}' already exists! Delete or choose to overwrite."
        raise ValueError(msg)

    with Path(output_file).open("w", encoding="utf-8") as f:
        json.dump(compartment_sets, f, indent=2)

    return output_file


def add_neuron_sets_to_sonata_circuit(
    circuit: "Circuit", neuron_sets: Mapping[str, "NeuronSet"]
) -> snap.Circuit:
    """Adds neuron sets to the node sets of a circuit's SONATA circuit object (in memory).

    Each neuron set is added under its dictionary key, which has to be its block name, along with
    the definitions a compound set needs. Returns the SONATA circuit object they were added to,
    which is the one to write out: `Circuit.sonata_circuit` loads a fresh object on every access,
    so a set added to one object is not seen through another. A neuron set clashing with a
    different node set of the same name is rejected by `add_node_set_to_circuit`.

    Raises:
        OBIONEError: If a dictionary key differs from the block name of its neuron set.
    """
    sonata_circuit = circuit.sonata_circuit
    for name, neuron_set in neuron_sets.items():
        if name != neuron_set.block_name:
            msg = (
                f"Neuron set name mismatch! The neuron set stored under {name!r} is named "
                f"{neuron_set.block_name!r}. Adding it with config.add(neuron_set, name=...) "
                f"ensures that they match."
            )
            raise OBIONEError(msg)
        neuron_set.add_node_set_definition_to_sonata_circuit(circuit, sonata_circuit)
    return sonata_circuit

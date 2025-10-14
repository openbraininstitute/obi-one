import json
import os
from pathlib import Path

import bluepysnap as snap


def add_node_set_to_circuit(
    sonata_circuit: snap.Circuit, node_set_dict: dict, *, overwrite_if_exists: bool = False
) -> None:
    """Adds the node set definition to a SONATA circuit object to make it accessible \
        (in-place).
    """
    existing_node_sets = sonata_circuit.node_sets.content
    if not overwrite_if_exists:
        for _k in node_set_dict:
            if _k in existing_node_sets:
                msg = f"Node set '{_k}' already exists!"
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
    output_file = Path(output_path) / file_name

    if not overwrite_if_exists and Path(output_file).exists():
        msg = f"Output file '{output_file}' already exists! Delete or choose to overwrite."
        raise ValueError(msg)

    with Path(output_file).open("w", encoding="utf-8") as f:
        json.dump(sonata_circuit.node_sets.content, f, indent=2)

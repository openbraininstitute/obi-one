import abc
import json
import logging
import os
from pathlib import Path

import bluepysnap as snap

from obi_one.core.block import Block
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.sonata_circuit_helpers import (
    add_node_set_to_circuit,
)

L = logging.getLogger(__name__)


class NeuronSet(Block, abc.ABC):
    """NeuronSet  [NEW - redefined].

    - New (abstract) base class for all neuron sets
    - No sampling
    - No node population (i.e., supports multi-population neuron sets!)
    """

    """Base class representing a neuron set which can be turned into a SONATA node set by either
    adding it to an existing SONATA circuit object (add_node_set_to_circuit) or writing it to a
    SONATA node set .json file (write_circuit_node_set_file).
    """

    @abc.abstractmethod
    def _get_expression(self, circuit: Circuit) -> dict:
        """Returns the SONATA node set expression (w/o subsampling)."""

    def add_node_set_definition_to_sonata_circuit(
        self, circuit: Circuit, sonata_circuit: snap.Circuit
    ) -> dict:
        nset_def = self.get_node_set_definition(circuit, force_resolve_ids=True)

        add_node_set_to_circuit(
            sonata_circuit, {self.block_name: nset_def}, overwrite_if_exists=False
        )

        return nset_def

    @staticmethod
    def _get_output_file(circuit: Circuit, file_name: str | None, output_path: str) -> str:
        if file_name is None:
            # Use circuit's node set file name by default
            file_name = os.path.split(circuit.sonata_circuit.config["node_sets_file"])[1]
        else:
            if not isinstance(file_name, str) or len(file_name) == 0:
                msg = (
                    "File name must be a non-empty string! Can be omitted to use default file name."
                )
                raise ValueError(msg)
            path = Path(file_name)
            if len(path.stem) == 0 or path.suffix.lower() != ".json":
                msg = "File name must be non-empty and of type .json!"
                raise ValueError(msg)
        output_file = Path(output_path) / file_name
        return output_file

    def to_node_set_file(
        self,
        circuit: Circuit,
        output_path: str,
        file_name: str | None = None,
        *,
        overwrite_if_exists: bool = False,
        append_if_exists: bool = False,
        force_resolve_ids: bool = False,
        init_empty: bool = False,
        optional_node_set_name: str | None = None,
    ) -> str:
        """Resolves the node set for a given circuit and writes it to a .json node set file."""
        if optional_node_set_name is not None:
            node_set_name = optional_node_set_name
        elif self.has_block_name():
            node_set_name = self.block_name
        else:
            msg = (
                "NeuronSet name must be set through the Simulation"
                " or optional_node_set_name parameter!"
            )
            raise ValueError(msg)

        output_file = self._get_output_file(circuit, file_name, output_path)

        if overwrite_if_exists and append_if_exists:
            msg = "Append and overwrite options are mutually exclusive!"
            raise ValueError(msg)
        expression = self.get_node_set_definition(circuit, force_resolve_ids=force_resolve_ids)
        if expression is None:
            msg = "Node set already exists in circuit, nothing to be done!"
            raise ValueError(msg)

        if not Path.exists(output_file) or overwrite_if_exists:
            # Create new node sets file, overwrite if existing
            if init_empty:
                # Initialize empty
                node_sets = {}
            else:
                # Initialize with circuit object's node sets
                node_sets = circuit.sonata_circuit.node_sets.content
                if node_set_name in node_sets:
                    msg = f"Node set '{node_set_name}' already exists in circuit '{circuit}'!"
                    raise ValueError(msg)
            node_sets.update({node_set_name: expression})

        elif Path.exists(output_file) and append_if_exists:
            # Append to existing node sets file
            with Path(output_file).open("r", encoding="utf-8") as f:
                node_sets = json.load(f)
                if node_set_name in node_sets:
                    msg = f"Appending not possible, node set '{node_set_name}' already exists!"
                    raise ValueError(msg)
                node_sets.update({node_set_name: expression})

        else:  # File existing but no option chosen
            msg = (
                f"Output file '{output_file}' already exists! Delete file or choose to append or"
                " overwrite."
            )
            raise ValueError(msg)

        with Path(output_file).open("w", encoding="utf-8") as f:
            json.dump(node_sets, f, indent=2)

        return output_file

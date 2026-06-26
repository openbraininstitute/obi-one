import abc
import json
import logging
import os
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

import bluepysnap as snap

from obi_one.core.block import Block
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.circuit_metrics import (
    TYPES_OF_BIOPHYS_NODES,
    TYPES_OF_POINT_NODES,
    TYPES_OF_VIRTUAL_NODES,
)
from obi_one.scientific.library.sonata_circuit_helpers import (
    add_node_set_to_circuit,
)

L = logging.getLogger(__name__)


class NeuronSetPopulationType(StrEnum):
    BIOPHYSICAL = "biophysical"
    POINT = "point"
    VIRTUAL = "virtual"
    NONVIRTUAL = "nonvirtual"
    ANY = "any"


class SonataPopulationType(StrEnum):
    BIOPHYSICAL = "biophysical"
    POINT = "point"
    VIRTUAL = "virtual"


class NeuronSet(Block, abc.ABC):
    """Base class representing a neuron set which can be turned into a SONATA node set by either
    adding it to an existing SONATA circuit object (add_node_set_to_circuit) or writing it to a
    SONATA node set .json file (write_circuit_node_set_file).

    Has a well-defined population type (including mixtures) and may span multiple node populations
    which are consistent with the defined type.
    """

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType]

    def get_neuron_set_population_type(self) -> NeuronSetPopulationType:
        return self._neuron_set_population_type

    def check_populations_in_circuit(self, circuit: Circuit) -> None:
        """Check if neuron set populations exist in circuit."""
        # Get neuron set populations
        nset_popul_names = self.get_populations(circuit)

        # Get circuit populations of the given type
        match self._neuron_set_population_type:
            case NeuronSetPopulationType.BIOPHYSICAL:
                incl_biophysical = True
                incl_point = incl_virtual = False
            case NeuronSetPopulationType.POINT:
                incl_point = True
                incl_biophysical = incl_virtual = False
            case NeuronSetPopulationType.VIRTUAL:
                incl_virtual = True
                incl_biophysical = incl_point = False
            case NeuronSetPopulationType.NONVIRTUAL:
                incl_biophysical = incl_point = True
                incl_virtual = False
            case NeuronSetPopulationType.ANY:
                incl_biophysical = incl_point = incl_virtual = True
            case _:
                msg = f"Unknown neuron set population type '{self._neuron_set_population_type}'!"
                raise ValueError(msg)
        circuit_popul_names = Circuit.get_node_population_names(
            circuit.sonata_circuit,
            incl_biophysical=incl_biophysical,
            incl_point=incl_point,
            incl_virtual=incl_virtual,
        )

        # Check circuit populations
        if not circuit_popul_names:
            msg = (
                f"Circuit '{circuit.name}' does not have any node populations"
                f" of type '{self._neuron_set_population_type}'!"
            )
            raise ValueError(msg)

        # Check neuron set populations
        missing = [f"'{p}'" for p in nset_popul_names if p not in circuit_popul_names]
        if missing:
            msg = (
                f"Node population(s) {', '.join(missing)}"
                f" of type '{self._neuron_set_population_type}'"
                f" not found in circuit '{circuit.name}'!"
                f" Available node populations: {', '.join(circuit_popul_names)}"
            )
            raise ValueError(msg)

    def get_population_types(self, circuit: Circuit) -> dict[str, SonataPopulationType]:
        """Returns population names and types included in the neuron set."""
        self.check_populations_in_circuit(circuit=circuit)

        popul_types = {}
        for pname in self.get_populations(circuit):
            if circuit.sonata_circuit.nodes[pname].type in TYPES_OF_BIOPHYS_NODES:
                ptype = SonataPopulationType.BIOPHYSICAL
            elif circuit.sonata_circuit.nodes[pname].type in TYPES_OF_VIRTUAL_NODES:
                ptype = SonataPopulationType.VIRTUAL
            elif circuit.sonata_circuit.nodes[pname].type in TYPES_OF_POINT_NODES:
                ptype = SonataPopulationType.POINT
            else:
                msg = f"Unknown SONATA population type for population '{pname}'!"
                raise ValueError(msg)
            popul_types[pname] = ptype
        return popul_types

    def has_biophysical_neurons(self, circuit: Circuit) -> bool:
        """Returns if the neuron set includes biophysical populations."""
        popul_types = self.get_population_types(circuit=circuit)
        return any(ptype == SonataPopulationType.BIOPHYSICAL for ptype in popul_types.values())

    def has_virtual_neurons(self, circuit: Circuit) -> bool:
        """Returns if the neuron set includes virtual populations."""
        popul_types = self.get_population_types(circuit=circuit)
        return any(ptype == SonataPopulationType.VIRTUAL for ptype in popul_types.values())

    def has_point_neurons(self, circuit: Circuit) -> bool:
        """Returns if the neuron set includes point populations."""
        popul_types = self.get_population_types(circuit=circuit)
        return any(ptype == SonataPopulationType.POINT for ptype in popul_types.values())

    @abc.abstractmethod
    def get_populations(self, circuit: Circuit) -> list[str]:
        """Returns population names included in the neuron set."""

    @abc.abstractmethod
    def get_node_set_definition(
        self, circuit: Circuit, *, force_resolve_ids: bool = False
    ) -> tuple[dict | list, dict]:
        """Returns the SONATA node set definition, optionally forcing to resolve individual IDs.

        Returns a tuple of (expression, combined) where:

        - expression (dict): A single SONATA node set expression. Examples:
            - Symbolic by population: {"population": "pop_name"}
            - Symbolic by properties: {"layer": "6", "synapse_class": "EXC"}
            - Resolved IDs: {"population": "pop_name", "node_id": [1, 2, 3]}

        - expression (list): A compound expression referencing multiple named node sets.
            Example: ["__ClassName__blockname__0__", "__ClassName__blockname__1__"]
            Each name must exist as a key in the combined dict.
            Also used for symbolic references to existing node sets: ["Layer6"]

        - combined (dict): Additional node set definitions needed by a compound expression.
            Example: {"__ClassName__blockname__0__": {"population": "A", "node_id": [...]},
                      "__ClassName__blockname__1__": {"population": "B", "node_id": [...]}}
            Empty ({}) when expression is a single dict.

        Args:
            circuit: The circuit to resolve the node set in.
            force_resolve_ids: If True, always resolve to explicit neuron IDs
                instead of preserving symbolic expressions.
        """

    @abc.abstractmethod
    def get_neuron_ids(self, circuit: Circuit) -> dict[str, list[int]]:
        """Returns list of neuron IDs per population."""

    @staticmethod
    def ids_to_node_set_definition(
        ids_per_npop: dict[str, list[int]],
        *,
        prefix: str = "nset",
        simplified: bool = True,
    ) -> tuple[dict | list, dict]:
        """Turns a dict of ID per population into a (compound) node set definition.

        May be simplified to a single expression, if possible.
        """
        expression = []
        combined = {}
        for idx, (npop, ids) in enumerate(ids_per_npop.items()):
            comb_key = f"{prefix}__{idx}__"
            combined[comb_key] = {
                "population": npop,
                "node_id": ids,
            }
            expression.append(comb_key)
        if simplified and len(expression) == 1:
            # Simplify to single expression
            expression = combined[expression[0]]
            combined = {}
        return expression, combined

    def add_node_set_definition_to_sonata_circuit(
        self, circuit: Circuit, sonata_circuit: snap.Circuit, *, force_resolve_ids: bool = False
    ) -> str:
        """Adds the node set definition to the corresponding SONATA circuit object."""
        if not self.has_block_name():
            msg = "Block name undefined. NeuronSet must be set through a Task."
            raise ValueError(msg)
        nset_def, compound_def = self.get_node_set_definition(
            circuit, force_resolve_ids=force_resolve_ids
        )
        nset_name = self.block_name
        nset_dict = compound_def | {nset_name: nset_def}

        add_node_set_to_circuit(sonata_circuit, nset_dict, overwrite_if_exists=False)
        return nset_name

    @staticmethod
    def _get_output_file(circuit: Circuit, file_name: str | None, output_path: str) -> Path:
        if file_name is None:
            # Use circuit's node set file name by default
            file_name = os.path.split(circuit.sonata_circuit.config["node_sets_file"])[1]
        else:
            if len(file_name) == 0:
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

    @staticmethod
    def _check_existing(new_node_sets: dict, existing_node_sets: dict) -> None:
        """Checks if new names already exist."""
        existing = [f"'{n}'" for n in new_node_sets if n in existing_node_sets]
        if existing:
            msg = f"Node set(s) {', '.join(existing)} already existing!"
            raise ValueError(msg)

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
    ) -> Path:
        """Resolves the neuron set for a given circuit and writes it to a .json node set file.

        The node set name in the output file defaults to
        ``__{ClassName}__{block_name}`` unless overridden via ``optional_node_set_name``.

        Args:
            circuit: The circuit to resolve the neuron set in.
            output_path: Directory where the output file will be written.
            file_name: Output file name. If None, uses the circuit's node set file name.
            overwrite_if_exists: If True, overwrite an existing file. Mutually exclusive
                with append_if_exists.
            append_if_exists: If True, append to an existing file. The node set name
                must not already exist in the file.
            force_resolve_ids: If True, resolve to explicit neuron IDs instead of
                preserving symbolic expressions.
            init_empty: If True, start with an empty file (ignore circuit's existing
                node sets). Only applies when creating a new file or overwriting.
            optional_node_set_name: Override the auto-generated node set name.

        Returns:
            Path to the written output file.

        Note:
            If the neuron set consists of a compound expression (list + combined dict),
            all entries from the combined dict are written to the file alongside the main
            node set entry. This ensures the compound expression references are resolvable.

        Raises:
            ValueError: If neither block_name nor optional_node_set_name is set,
                if overwrite and append are both True, or if the file exists without
                either option specified.
        """
        if optional_node_set_name is not None:
            node_set_name = optional_node_set_name
        elif self.has_block_name():
            node_set_name = f"__{self.__class__.__name__}__{self.block_name}"
        else:
            msg = "NeuronSet name must be set through a Task or optional_node_set_name parameter!"
            raise ValueError(msg)

        output_file = NeuronSet._get_output_file(circuit, file_name, output_path)

        if overwrite_if_exists and append_if_exists:
            msg = "Append and overwrite options are mutually exclusive!"
            raise ValueError(msg)

        nset_def, compound_def = self.get_node_set_definition(
            circuit, force_resolve_ids=force_resolve_ids
        )
        nset_dict = compound_def | {node_set_name: nset_def}

        if not output_file.exists() or overwrite_if_exists:
            # Create new node sets file, overwrite if existing
            if init_empty:  # noqa: SIM108
                # Initialize empty
                node_sets = {}
            else:
                # Initialize with circuit object's node sets
                node_sets = circuit.sonata_circuit.node_sets.content

        elif output_file.exists() and append_if_exists:
            # Append to existing node sets file
            with output_file.open("r", encoding="utf-8") as f:
                node_sets = json.load(f)

        else:  # File existing but no option chosen
            msg = (
                f"Output file '{output_file}' already exists! Delete file or choose to append or"
                " overwrite."
            )
            raise ValueError(msg)

        NeuronSet._check_existing(nset_dict, node_sets)
        node_sets.update(nset_dict)

        with output_file.open("w", encoding="utf-8") as f:
            json.dump(node_sets, f, indent=2)

        return output_file

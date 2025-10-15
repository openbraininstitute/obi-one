import abc
import contextlib
import json
import logging
import os
from pathlib import Path
from typing import Annotated

import bluepysnap as snap
import numpy as np
from pydantic import Field, NonNegativeFloat

from obi_one.core.block import Block
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.sonata_circuit_helpers import (
    add_node_set_to_circuit,
)

L = logging.getLogger("obi-one")
_NBS1_VPM_NODE_POP = "VPM"
_NBS1_POM_NODE_POP = "POm"
_RCA1_CA3_NODE_POP = "CA3_projections"

_ALL_NODE_SET = "All"
_EXCITATORY_NODE_SET = "Excitatory"
_INHIBITORY_NODE_SET = "Inhibitory"

_MAX_PERCENT = 100.0

CircuitNode = Annotated[str, Field(min_length=1)]
NodeSetType = CircuitNode | list[CircuitNode]

with contextlib.suppress(ImportError):  # Try to import connalysis
    pass


class AbstractNeuronSet(Block, abc.ABC):
    """Base class representing a neuron set which can be turned into a SONATA node set by either
    adding it to an existing SONATA circuit object (add_node_set_to_circuit) or writing it to a
    SONATA node set .json file (write_circuit_node_set_file).
    """

    sample_percentage: (
        Annotated[NonNegativeFloat, Field(le=100)]
        | Annotated[list[Annotated[NonNegativeFloat, Field(le=100)]], Field(min_length=1)]
    ) = Field(
        default=100.0,
        title="Sample (Percentage)",
        description="Percentage of neurons to sample between 0 and 100%",
        units="%",
    )

    sample_seed: int | list[int] = Field(
        default=1, title="Sample Seed", description="Seed for random sampling."
    )

    @abc.abstractmethod
    def _get_expression(self, circuit: Circuit, population: str) -> dict:
        """Returns the SONATA node set expression (w/o subsampling)."""

    @staticmethod
    def check_population(
        circuit: Circuit, population: str | None, *, ignore_none: bool = False
    ) -> None:
        if population is None:
            if ignore_none:
                return
            msg = "Must specify a node population name!"
            raise ValueError(msg)
        if population not in Circuit.get_node_population_names(circuit.sonata_circuit):
            msg = f"Node population '{population}' not found in circuit '{circuit}'!"
            raise ValueError(msg)

    def add_node_set_definition_to_sonata_circuit(
        self, circuit: Circuit, sonata_circuit: snap.Circuit
    ) -> None:
        nset_def = self.get_node_set_definition(
            circuit, circuit.default_population_name, force_resolve_ids=True
        )

        add_node_set_to_circuit(
            sonata_circuit, {self.block_name: nset_def}, overwrite_if_exists=False
        )

    def get_population(self, population: str | None = None) -> str:
        return self._population(population)

    def _population(self, population: str | None = None) -> str:  # noqa: PLR6301
        return population

    def _resolve_ids(self, circuit: Circuit, population: str | None = None) -> list[int]:
        """Returns the full list of neuron IDs (w/o subsampling)."""
        population = self._population(population)
        c = circuit.sonata_circuit
        expression = self._get_expression(circuit, population)
        name = "__TMP_NODE_SET__"
        add_node_set_to_circuit(c, {name: expression})

        try:
            node_ids = c.nodes[population].ids(name)
        except snap.BluepySnapError as e:
            # In case of an error, return empty list
            L.warning(e)
            node_ids = []

        return node_ids

    def get_neuron_ids(self, circuit: Circuit, population: str | None = None) -> np.ndarray:
        """Returns list of neuron IDs (with subsampling, if specified)."""
        self.enforce_no_multi_param()
        population = self._population(population)
        self.check_population(circuit, population)
        ids = np.array(self._resolve_ids(circuit, population))
        if len(ids) > 0 and self.sample_percentage < _MAX_PERCENT:
            rng = np.random.default_rng(self.sample_seed)

            num_sample = np.round((self.sample_percentage / 100.0) * len(ids)).astype(int)

            ids = ids[rng.permutation([True] * num_sample + [False] * (len(ids) - num_sample))]

        if len(ids) == 0:
            L.warning("Neuron set empty!")

        return ids

    def get_node_set_definition(
        self, circuit: Circuit, population: str | None = None, *, force_resolve_ids: bool = False
    ) -> dict:
        """Returns the SONATA node set definition, optionally forcing to resolve individual \
            IDs.
        """
        self.enforce_no_multi_param()
        population = self._population(population)
        if self.sample_percentage == _MAX_PERCENT and not force_resolve_ids:
            # Symbolic expression can be preserved
            self.check_population(circuit, population, ignore_none=True)
            expression = self._get_expression(circuit, population)
        else:
            # Individual IDs need to be resolved
            self.check_population(circuit, population)
            expression = {
                "population": population,
                "node_id": self.get_neuron_ids(circuit, population).tolist(),
            }

        return expression

    def population_type(self, circuit: Circuit, population: str | None = None) -> str:
        """Returns the population type (i.e. biophysical / virtual)."""
        return circuit.sonata_circuit.nodes[self._population(population)].type

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
        population: str,
        output_path: str,
        file_name: str | None = None,
        *,
        overwrite_if_exists: bool = False,
        append_if_exists: bool = False,
        force_resolve_ids: bool = False,
        init_empty: bool = False,
        optional_node_set_name: str | None = None,
    ) -> str:
        """Resolves the node set for a given circuit/population and writes it to a .json node \
            set file.
        """
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

        output_file = AbstractNeuronSet._get_output_file(circuit, file_name, output_path)

        if overwrite_if_exists and append_if_exists:
            msg = "Append and overwrite options are mutually exclusive!"
            raise ValueError(msg)
        population = self._population(population)
        expression = self.get_node_set_definition(
            circuit, population, force_resolve_ids=force_resolve_ids
        )
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


class NeuronSet(AbstractNeuronSet):
    """Extension of abstract neuron set which allows to specify the node population upon creation.

    This is optional, all functions requiring a node population can be optionally called with the
    name of a default population to be used in case no name was set upon creation.
    """

    node_population: str | list[str] | None = None

    def _population(self, population: str | None = None) -> str:
        if (
            population is not None
            and self.node_population is not None
            and population != self.node_population
        ):
            L.warning(
                "Node population %s has been set for this block and will be used. Ignoring %s",
                self.node_population,
                population,
            )
        population = self.node_population or population
        if population is None:
            msg = "Must specify name of a node population to resolve the NeuronSet!"
            raise ValueError(msg)
        return population

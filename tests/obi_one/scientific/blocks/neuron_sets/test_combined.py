import json
import re
from pathlib import Path

import pytest

import obi_one as obi
from obi_one.scientific.blocks.neuron_sets.combined import CombinedNeuronSet, SetOperation
from obi_one.scientific.blocks.neuron_sets.predefined import PredefinedNeuronSet
from obi_one.scientific.unions.unions_neuron_sets import BiophysicalNeuronSetReference

from tests.utils import CIRCUIT_DIR

CIRCUIT_NAME = "N_10__top_nodes_dim6"

# Neuron IDs each predefined node set resolves to in the default population of the test circuit:
#   L6_BPC -> [1, 2]      L6_IPC -> [3, 4, 5]      L6_TPC:A -> [6, 7, 8, 9]
#   Layer6 / Excitatory -> [1..9]


@pytest.fixture(scope="module")
def circuit():
    return obi.Circuit(
        name=CIRCUIT_NAME,
        path=str(CIRCUIT_DIR / CIRCUIT_NAME / "circuit_config.json"),
    )


def _resolved_ref(neuron_set: PredefinedNeuronSet, name: str) -> BiophysicalNeuronSetReference:
    """Return a resolved reference to a named neuron set.

    Mirrors what a Task/config wiring (``fill_block_references_and_names``) produces: the block
    name is set and the reference's block is resolved so that ``_resolve_refs`` can read it back.
    """
    neuron_set.set_block_name(name)
    ref = BiophysicalNeuronSetReference(block_name=name, block_dict_name="neuron_sets")
    ref.block = neuron_set
    return ref


def _combined_neuron_set(
    base_node_set: str,
    combined_with: list[tuple[str, SetOperation]],
    *,
    name: str = "Combined",
) -> CombinedNeuronSet:
    """Build a resolved CombinedNeuronSet from predefined circuit node sets.

    Args:
        base_node_set: Name of the circuit node set used as the base neuron set.
        combined_with: Sequence of (node_set_name, operation) applied in order.
        name: Block name assigned to the combined neuron set.
    """
    base_ref = _resolved_ref(PredefinedNeuronSet(node_set=base_node_set), base_node_set)
    combine_refs = [
        (_resolved_ref(PredefinedNeuronSet(node_set=node_set), node_set), operation)
        for node_set, operation in combined_with
    ]
    neuron_set = CombinedNeuronSet(base_neuron_set=base_ref, combined_with=combine_refs)
    neuron_set.set_block_name(name)
    return neuron_set


@pytest.mark.parametrize(
    ("base_node_set", "combined_with", "expected_ids"),
    [
        # union of L6_BPC and L6_TPC:A
        ("L6_BPC", [("L6_TPC:A", SetOperation.UNION)], [1, 2, 6, 7, 8, 9]),
        # intersection of Layer6 and L6_IPC
        ("Layer6", [("L6_IPC", SetOperation.INTERSECT)], [3, 4, 5]),
        # difference: Layer6 minus L6_IPC
        ("Layer6", [("L6_IPC", SetOperation.DIFF)], [1, 2, 6, 7, 8, 9]),
        # chained unions applied in order: union(L6_BPC, L6_IPC, L6_TPC:A)
        (
            "L6_BPC",
            [("L6_IPC", SetOperation.UNION), ("L6_TPC:A", SetOperation.UNION)],
            [1, 2, 3, 4, 5, 6, 7, 8, 9],
        ),
        # chained mixed operations: (Excitatory minus L6_BPC) intersect L6_IPC
        (
            "Excitatory",
            [("L6_BPC", SetOperation.DIFF), ("L6_IPC", SetOperation.INTERSECT)],
            [3, 4, 5],
        ),
    ],
)
def test_combined_neuron_set_operations(circuit, base_node_set, combined_with, expected_ids):
    neuron_set = _combined_neuron_set(base_node_set, combined_with)
    neuron_ids = neuron_set.get_neuron_ids(circuit)[circuit.default_population_name]
    assert neuron_ids == expected_ids


def test_combined_neuron_set_missing_node_set_raises(circuit):
    neuron_set = _combined_neuron_set("L6_BPC", [("L6_TPC:AA", SetOperation.UNION)])
    with pytest.raises(
        ValueError,
        match=re.escape(f"Node set 'L6_TPC:AA' not found in circuit '{CIRCUIT_NAME}'."),
    ):
        neuron_set.get_neuron_ids(circuit)


def test_combined_neuron_set_node_set_definition(circuit):
    neuron_set = _combined_neuron_set("L6_BPC", [("L6_TPC:A", SetOperation.UNION)])

    # A union-only combination preserves a symbolic compound expression referencing its members.
    expression, compound = neuron_set.get_node_set_definition(circuit)
    assert expression == ["__CombinedNeuronSet__L6_BPC", "__CombinedNeuronSet__L6_TPC:A"]
    assert compound == {
        "__CombinedNeuronSet__L6_BPC": ["L6_BPC"],
        "__CombinedNeuronSet__L6_TPC:A": ["L6_TPC:A"],
    }

    # Forcing ID resolution collapses to explicit neuron IDs in a single population.
    expression, compound = neuron_set.get_node_set_definition(circuit, force_resolve_ids=True)
    assert expression == {
        "population": circuit.default_population_name,
        "node_id": [1, 2, 6, 7, 8, 9],
    }
    assert compound == {}


def test_write_to_node_set_file(circuit, tmp_path):
    output_dir = str(tmp_path)
    population = circuit.default_population_name
    neuron_set = _combined_neuron_set("L6_BPC", [("L6_TPC:A", SetOperation.UNION)], name="L123")

    # Write a new file.
    nset_file = neuron_set.to_node_set_file(
        circuit,
        output_dir,
        force_resolve_ids=True,
        overwrite_if_exists=False,
        optional_node_set_name="L123",
    )
    assert Path(nset_file).exists()

    # Write again w/o overwriting --> Must raise an error.
    with pytest.raises(
        ValueError,
        match=re.escape(
            f"Output file '{tmp_path / 'node_sets.json'}' already exists!"
            " Delete file or choose to append or overwrite."
        ),
    ):
        neuron_set.to_node_set_file(
            circuit,
            output_dir,
            force_resolve_ids=True,
            overwrite_if_exists=False,
            optional_node_set_name="L123",
        )

    # Write again with overwriting --> No error.
    nset_file = neuron_set.to_node_set_file(
        circuit,
        output_dir,
        force_resolve_ids=True,
        overwrite_if_exists=True,
        optional_node_set_name="L123",
    )
    assert Path(nset_file).exists()

    # Append to existing file, but name already exists --> Must raise an error.
    with pytest.raises(ValueError, match=re.escape("'L123' already existing!")):
        neuron_set.to_node_set_file(
            circuit,
            output_dir,
            force_resolve_ids=True,
            append_if_exists=True,
            optional_node_set_name="L123",
        )

    # Append a new node set to the existing file.
    other_neuron_set = _combined_neuron_set("L6_BPC", [("L6_IPC", SetOperation.UNION)], name="L456")
    nset_file = other_neuron_set.to_node_set_file(
        circuit,
        output_dir,
        force_resolve_ids=True,
        append_if_exists=True,
        optional_node_set_name="L456",
    )
    assert Path(nset_file).exists()

    # Check that both new node sets exist in the .json file with resolved IDs.
    with Path(nset_file).open(encoding="utf-8") as f:
        node_sets = json.load(f)

    assert node_sets["L123"] == {"population": population, "node_id": [1, 2, 6, 7, 8, 9]}
    assert node_sets["L456"] == {"population": population, "node_id": [1, 2, 3, 4, 5]}

    # Check that original node sets are preserved in the new node sets file.
    orig_node_sets = circuit.sonata_circuit.node_sets.content
    for k, v in orig_node_sets.items():
        assert k in node_sets
        assert node_sets[k] == v

    # Check that original node sets are unchanged.
    assert "L123" not in orig_node_sets
    assert "L456" not in orig_node_sets


def test_write_to_node_set_file_preserves_symbolic_compound(circuit, tmp_path):
    """A symbolic (union-only) combined set writes its member node sets alongside the compound."""
    neuron_set = _combined_neuron_set("L6_BPC", [("L6_TPC:A", SetOperation.UNION)], name="L123")
    nset_file = neuron_set.to_node_set_file(
        circuit,
        str(tmp_path),
        overwrite_if_exists=False,
        optional_node_set_name="L123",
    )

    node_sets = json.loads(Path(nset_file).read_text(encoding="utf-8"))

    # The compound expression references the auto-named member node sets, written alongside it.
    assert node_sets["L123"] == ["__CombinedNeuronSet__L6_BPC", "__CombinedNeuronSet__L6_TPC:A"]
    assert node_sets["__CombinedNeuronSet__L6_BPC"] == ["L6_BPC"]
    assert node_sets["__CombinedNeuronSet__L6_TPC:A"] == ["L6_TPC:A"]


@pytest.mark.parametrize(
    ("base_node_set", "combined_with"),
    [
        # Same population
        ("L6_BPC", [("L6_TPC:A", SetOperation.UNION)]),
        ("Layer6", [("L6_IPC", SetOperation.INTERSECT)]),
        ("Layer6", [("L6_IPC", SetOperation.DIFF)]),
        # Chained operations
        ("L6_BPC", [("L6_IPC", SetOperation.UNION), ("L6_TPC:A", SetOperation.DIFF)]),
        # Cross-population union (triggers empty-list fallback per population)
        (
            "proj_Thalamocortical_VPM_Source",
            [("proj_Thalamocortical_POM_Source", SetOperation.UNION)],
        ),
    ],
)
def test_combined_neuron_ids_are_int(circuit, base_node_set, combined_with):
    """All neuron IDs returned by get_neuron_ids must be Python int, never float."""
    neuron_set = _combined_neuron_set(base_node_set, combined_with)
    ids_per_pop = neuron_set.get_neuron_ids(circuit)
    for pop, ids in ids_per_pop.items():
        assert all(isinstance(i, int) for i in ids), f"Non-int IDs in population '{pop}': {ids}"

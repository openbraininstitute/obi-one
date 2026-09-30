"""Tests ported from the neuron_sets example notebooks.

The notebooks under ``examples/obi_one/scientific/blocks/neuron_sets`` are demonstrative (they
print rather than assert), so they only catch crashes, not regressions. This module turns the
scenarios they walk through into checked tests against the same ``N_10__top_nodes_dim6`` circuit
the notebooks use, so the documented behaviour is actually pinned.

Where a scenario is already asserted elsewhere (see ``test_predefined``/``test_property``/
``test_combined``/``test_population``/``test_specific``), it is not duplicated here; this file
concentrates on the end-to-end scenarios the notebooks add on top: recursive-cycle detection,
cross-population virtual unions, and chained multi-operation combinations.

Reference IDs for the default population ``S1nonbarrel_neurons`` (from test_combined.py):
    L6_BPC -> [1, 2]   L6_IPC -> [3, 4, 5]   L6_TPC:A -> [6, 7, 8, 9]
    Layer6 / Excitatory -> [1..9]
"""

import re

import pytest

import obi_one as obi
from obi_one.scientific.blocks.neuron_sets.combined import (
    BiophysicalCombinedNeuronSet,
    SetOperation,
    VirtualCombinedNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.population import (
    BiophysicalPopulationNeuronSet,
    VirtualPopulationNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.predefined import (
    BiophysicalPopulationPredefinedNeuronSet,
    VirtualPopulationPredefinedNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.property import (
    BiophysicalPopulationPropertyNeuronSet,
    NeuronPropertyFilter,
)
from obi_one.scientific.unions_and_references.neuron_sets import (
    BiophysicalNeuronSetReference,
    VirtualNeuronSetReference,
)

from tests.utils import CIRCUIT_DIR

CIRCUIT_NAME = "N_10__top_nodes_dim6"
BIO_POP = "S1nonbarrel_neurons"


@pytest.fixture(scope="module")
def circuit():
    return obi.Circuit(
        name=CIRCUIT_NAME,
        path=str(CIRCUIT_DIR / CIRCUIT_NAME / "circuit_config.json"),
    )


def _bio_ref(neuron_set, name: str) -> BiophysicalNeuronSetReference:
    """Resolved biophysical reference, mirroring what config wiring produces."""
    neuron_set.set_block_name(name)
    ref = BiophysicalNeuronSetReference(block_dict_name="neuron_sets", block_name=name)
    ref.block = neuron_set
    return ref


def _virtual_ref(neuron_set, name: str) -> VirtualNeuronSetReference:
    neuron_set.set_block_name(name)
    ref = VirtualNeuronSetReference(block_dict_name="neuron_sets", block_name=name)
    ref.block = neuron_set
    return ref


# --- neuron_set_example.ipynb -----------------------------------------------------------------


def test_population_neuron_set_full_is_symbolic(circuit):
    """Notebook cell 9: a whole biophysical population stays a symbolic population clause."""
    nset = BiophysicalPopulationNeuronSet(population=BIO_POP)
    nset.set_block_name("whole_pop")
    nset_def, combined = nset.get_node_set_definition(circuit)
    assert nset_def == {"population": BIO_POP}
    assert combined == {}


def test_population_neuron_set_sampled_resolves_to_ids(circuit):
    """Notebook cell 7: sub-sampling has no symbolic form, so it resolves to explicit ids."""
    nset = BiophysicalPopulationNeuronSet(population=BIO_POP, sample_percentage=50, sample_seed=1)
    nset.set_block_name("half_pop")
    nset_def, _ = nset.get_node_set_definition(circuit)
    assert nset_def["population"] == BIO_POP
    assert "node_id" in nset_def
    # A 50% sample of a 10-neuron population selects a strict, non-empty subset.
    assert 0 < len(nset_def["node_id"]) < 10


def test_predefined_population_pinned_is_symbolic(circuit):
    """Notebook cell 13 (without sampling): predefined pinned to a population stays symbolic."""
    nset = BiophysicalPopulationPredefinedNeuronSet(node_set="Layer6", population=BIO_POP)
    nset.set_block_name("layer6_bio")
    nset_def, _ = nset.get_node_set_definition(circuit)
    assert isinstance(nset_def, dict)
    assert nset_def.get("population") == BIO_POP
    assert "node_id" not in nset_def


def test_predefined_wrong_population_type_raises(circuit):
    """Notebook cell 14: a virtual predefined set pinned to a biophysical population is invalid."""
    nset = VirtualPopulationPredefinedNeuronSet(node_set="Layer6", population=BIO_POP)
    nset.set_block_name("bad_pop_type")
    with pytest.raises(ValueError, match="population"):
        nset.get_node_set_definition(circuit)


def test_property_neuron_set_multi_clause_is_symbolic(circuit):
    """Notebook cell 18: a multi-property filter becomes a single symbolic multi-clause object."""
    nset = BiophysicalPopulationPropertyNeuronSet(
        population=BIO_POP,
        property_filter=NeuronPropertyFilter(
            filter_dict={"layer": ["6"], "synapse_class": ["EXC"]}
        ),
    )
    nset.set_block_name("l6_exc")
    nset_def, combined = nset.get_node_set_definition(circuit)
    assert nset_def == {"layer": "6", "synapse_class": "EXC", "population": BIO_POP}
    assert combined == {}
    assert "node_id" not in nset_def


def test_property_neuron_set_added_to_sonata_resolves(circuit):
    """Notebook cell 25: a symbolic property set added to the SONATA circuit resolves via snap."""
    nset = BiophysicalPopulationPropertyNeuronSet(
        population=BIO_POP,
        property_filter=NeuronPropertyFilter(
            filter_dict={"layer": ["6"], "synapse_class": ["EXC"]}
        ),
    )
    nset.set_block_name("L6_EXC")

    sonata_circuit = circuit.sonata_circuit
    nset_name = nset.add_node_set_definition_to_sonata_circuit(circuit, sonata_circuit)

    # The set is registered symbolically...
    assert sonata_circuit.node_sets.content[nset_name] == {
        "layer": "6",
        "synapse_class": "EXC",
        "population": BIO_POP,
    }
    # ...and libsonata materializes it to the same ids the block computes directly.
    via_snap = sonata_circuit.nodes[BIO_POP].ids(nset_name).tolist()
    assert via_snap == nset.get_neuron_ids(circuit)[BIO_POP]


# --- combined_neuron_set_example.ipynb --------------------------------------------------------


def test_combined_union_symbolic_definition(circuit):
    """Notebook cell 14: a union of two population-pinned predefined sets stays symbolic."""
    a = BiophysicalPopulationPredefinedNeuronSet(node_set="Layer3", population=BIO_POP)
    b = BiophysicalPopulationPredefinedNeuronSet(node_set="Layer6", population=BIO_POP)
    combined = BiophysicalCombinedNeuronSet(
        base_neuron_set=_bio_ref(a, "nset_a"),
        combined_with=[(_bio_ref(b, "nset_b"), SetOperation.UNION)],
    )
    combined.set_block_name("union_ab")

    expression, compound = combined.get_node_set_definition(circuit)
    assert expression == [
        "__BiophysicalCombinedNeuronSet__nset_a",
        "__BiophysicalCombinedNeuronSet__nset_b",
    ]
    # No explicit ids at the top level: the members are inlined symbolically.
    assert all(isinstance(v, dict) and "node_id" not in v for v in compound.values())


def test_combined_intersect_resolves_to_ids(circuit):
    """Notebook cell 9: intersection has no SONATA construct, so it resolves to explicit ids."""
    a = BiophysicalPopulationPredefinedNeuronSet(node_set="Layer6", population=BIO_POP)
    b = BiophysicalPopulationPredefinedNeuronSet(node_set="L6_IPC", population=BIO_POP)
    combined = BiophysicalCombinedNeuronSet(
        base_neuron_set=_bio_ref(a, "nset_a"),
        combined_with=[(_bio_ref(b, "nset_b"), SetOperation.INTERSECT)],
    )
    combined.set_block_name("intersect_ab")

    expression, _ = combined.get_node_set_definition(circuit)
    assert expression == {"population": BIO_POP, "node_id": [3, 4, 5]}


def test_combined_diff_ids(circuit):
    """Notebook cell 10: A minus B (Layer6 - L6_IPC) resolves to the expected complement."""
    a = BiophysicalPopulationPredefinedNeuronSet(node_set="Layer6", population=BIO_POP)
    b = BiophysicalPopulationPredefinedNeuronSet(node_set="L6_IPC", population=BIO_POP)
    combined = BiophysicalCombinedNeuronSet(
        base_neuron_set=_bio_ref(a, "nset_a"),
        combined_with=[(_bio_ref(b, "nset_b"), SetOperation.DIFF)],
    )
    combined.set_block_name("diff_ab")
    assert combined.get_neuron_ids(circuit)[BIO_POP] == [1, 2, 6, 7, 8, 9]


def test_combined_recursive_cycle_raises(circuit):
    """Notebook cell 12: a cycle between two combined sets is rejected, not looped forever."""
    a = BiophysicalPopulationPredefinedNeuronSet(node_set="All", population=BIO_POP)
    b = BiophysicalPopulationPredefinedNeuronSet(node_set="All", population=BIO_POP)

    x = BiophysicalCombinedNeuronSet(
        base_neuron_set=_bio_ref(a, "a"),
        combined_with=[(_bio_ref(b, "b"), SetOperation.UNION)],
    )
    x.set_block_name("cx")
    y = BiophysicalCombinedNeuronSet(
        base_neuron_set=_bio_ref(a, "a"),
        combined_with=[(_bio_ref(b, "b"), SetOperation.UNION)],
    )
    y.set_block_name("cy")

    ref_x = BiophysicalNeuronSetReference(block_dict_name="neuron_sets", block_name="cx")
    ref_x.block = x
    ref_y = BiophysicalNeuronSetReference(block_dict_name="neuron_sets", block_name="cy")
    ref_y.block = y
    x.combined_with = [(ref_y, SetOperation.UNION)]
    y.combined_with = [(ref_x, SetOperation.UNION)]

    with pytest.raises(ValueError, match=re.escape("Recursive loop in combined neuron set 'cx'!")):
        x.get_neuron_ids(circuit)


def test_combined_virtual_cross_population_union_is_symbolic(circuit):
    """Notebook cell 16: a union across two virtual populations stays symbolic per population."""
    pom = VirtualPopulationNeuronSet(population="POm")
    vpm = VirtualPopulationNeuronSet(population="VPM")
    combined = VirtualCombinedNeuronSet(
        base_neuron_set=_virtual_ref(pom, "nset_pom"),
        combined_with=[(_virtual_ref(vpm, "nset_vpm"), SetOperation.UNION)],
    )
    combined.set_block_name("virtual_union")

    expression, compound = combined.get_node_set_definition(circuit)
    assert expression == [
        "__VirtualCombinedNeuronSet__nset_pom",
        "__VirtualCombinedNeuronSet__nset_vpm",
    ]
    assert compound == {
        "__VirtualCombinedNeuronSet__nset_pom": {"population": "POm"},
        "__VirtualCombinedNeuronSet__nset_vpm": {"population": "VPM"},
    }
    # Both virtual populations are represented in the resolved ids.
    ids = combined.get_neuron_ids(circuit)
    assert set(ids) == {"POm", "VPM"}
    assert ids["POm"]
    assert ids["VPM"]


def test_combined_chained_multi_operation_resolves_to_ids(circuit):
    """Notebook cell 18: (Set1 UNION Set2) DIFF Set3 with any non-union op resolves to ids."""
    n1 = BiophysicalPopulationPredefinedNeuronSet(node_set="Layer6", population=BIO_POP)
    n2 = BiophysicalPopulationPredefinedNeuronSet(node_set="L6_BPC", population=BIO_POP)
    n3 = BiophysicalPopulationPredefinedNeuronSet(node_set="L6_IPC", population=BIO_POP)
    combined = BiophysicalCombinedNeuronSet(
        base_neuron_set=_bio_ref(n1, "n1"),
        combined_with=[
            (_bio_ref(n2, "n2"), SetOperation.UNION),
            (_bio_ref(n3, "n3"), SetOperation.DIFF),
        ],
    )
    combined.set_block_name("multi_combined")

    # (Layer6[1..9] UNION L6_BPC[1,2]) DIFF L6_IPC[3,4,5] = [1,2,6,7,8,9]
    expression, _ = combined.get_node_set_definition(circuit)
    assert expression == {"population": BIO_POP, "node_id": [1, 2, 6, 7, 8, 9]}

"""Tests for neuron_sets combined neuron sets."""

import numpy as np
import pytest

import obi_one as obi
from obi_one.scientific.blocks.neuron_sets.combined import (
    BiophysicalCombinedNeuronSet,
    SetOperation,
)
from obi_one.scientific.blocks.neuron_sets.population import (
    VirtualPopulationNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.predefined import (
    BiophysicalPopulationPredefinedNeuronSet,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    BiophysicalNeuronSetReference,
    VirtualNeuronSetReference,
)

from tests.utils import CIRCUIT_DIR, MATRIX_DIR

CIRCUIT_NAME = "N_10__top_nodes_dim6"


@pytest.fixture
def circuit():
    return obi.Circuit(
        name=CIRCUIT_NAME,
        path=str(CIRCUIT_DIR / CIRCUIT_NAME / "circuit_config.json"),
        matrix_path=str(MATRIX_DIR / CIRCUIT_NAME / "connectivity_matrix.h5"),
    )


@pytest.fixture
def nset_a():
    """L6_BPC node set."""
    nset = BiophysicalPopulationPredefinedNeuronSet(
        node_set="L6_BPC", population="S1nonbarrel_neurons"
    )
    nset.set_block_name("nset_a")
    return nset


@pytest.fixture
def nset_b():
    """L6_TPC:A node set."""
    nset = BiophysicalPopulationPredefinedNeuronSet(
        node_set="L6_TPC:A", population="S1nonbarrel_neurons"
    )
    nset.set_block_name("nset_b")
    return nset


@pytest.fixture
def ref_a(nset_a):
    """BlockReference wrapping nset_a."""
    ref = BiophysicalNeuronSetReference(block_dict_name="neuron_sets", block_name="nset_a")
    ref.block = nset_a
    return ref


@pytest.fixture
def ref_b(nset_b):
    """BlockReference wrapping nset_b."""
    ref = BiophysicalNeuronSetReference(block_dict_name="neuron_sets", block_name="nset_b")
    ref.block = nset_b
    return ref


def test_combined_union(circuit, ref_a, ref_b, nset_a, nset_b):
    """Test union operation combines IDs from both sets."""
    combined = BiophysicalCombinedNeuronSet(
        base_neuron_set=ref_a, combined_with=ref_b, operation=SetOperation.UNION
    )
    combined.set_block_name("union_ab")

    ids_a = nset_a.get_neuron_ids(circuit)["S1nonbarrel_neurons"]
    ids_b = nset_b.get_neuron_ids(circuit)["S1nonbarrel_neurons"]
    expected = sorted(set(ids_a) | set(ids_b))

    result = combined.get_neuron_ids(circuit)
    assert "S1nonbarrel_neurons" in result
    np.testing.assert_array_equal(sorted(result["S1nonbarrel_neurons"]), expected)


def test_combined_intersection(circuit, ref_a, ref_b, nset_a, nset_b):
    """Test intersection operation returns common IDs."""
    combined = BiophysicalCombinedNeuronSet(
        base_neuron_set=ref_a, combined_with=ref_b, operation=SetOperation.INTERSECT
    )
    combined.set_block_name("intersect_ab")

    ids_a = nset_a.get_neuron_ids(circuit)["S1nonbarrel_neurons"]
    ids_b = nset_b.get_neuron_ids(circuit)["S1nonbarrel_neurons"]
    expected = sorted(set(ids_a) & set(ids_b))

    result = combined.get_neuron_ids(circuit)
    assert "S1nonbarrel_neurons" in result
    np.testing.assert_array_equal(sorted(result["S1nonbarrel_neurons"]), expected)


def test_combined_difference(circuit, ref_a, ref_b, nset_a, nset_b):
    """Test difference operation returns A - B."""
    combined = BiophysicalCombinedNeuronSet(
        base_neuron_set=ref_a, combined_with=ref_b, operation=SetOperation.DIFF
    )
    combined.set_block_name("diff_ab")

    ids_a = nset_a.get_neuron_ids(circuit)["S1nonbarrel_neurons"]
    ids_b = nset_b.get_neuron_ids(circuit)["S1nonbarrel_neurons"]
    expected = sorted(set(ids_a) - set(ids_b))

    result = combined.get_neuron_ids(circuit)
    np.testing.assert_array_equal(sorted(result["S1nonbarrel_neurons"]), expected)


def test_combined_union_symbolic(circuit, ref_a, ref_b):
    """Test union produces symbolic expression (not resolved IDs)."""
    combined = BiophysicalCombinedNeuronSet(
        base_neuron_set=ref_a, combined_with=ref_b, operation=SetOperation.UNION
    )
    combined.set_block_name("union_sym")

    nset_def, combined_defs = combined.get_node_set_definition(circuit)
    # Union -> symbolic compound expression
    assert isinstance(nset_def, list)
    assert len(nset_def) == 2
    # Every key in the expression list must exist in combined_defs
    assert set(nset_def) == set(combined_defs.keys())


def test_combined_intersect_resolves_ids(circuit, ref_a, ref_b):
    """Test intersection always resolves IDs (non-union operation)."""
    combined = BiophysicalCombinedNeuronSet(
        base_neuron_set=ref_a, combined_with=ref_b, operation=SetOperation.INTERSECT
    )
    combined.set_block_name("intersect_resolve")

    nset_def, _ = combined.get_node_set_definition(circuit)
    # Non-union -> resolved IDs (simplified to dict for single population)
    assert isinstance(nset_def, dict)
    assert "node_id" in nset_def


def test_combined_missing_ref(circuit, ref_a):
    """Test that None reference raises."""
    combined = BiophysicalCombinedNeuronSet(
        base_neuron_set=ref_a, combined_with=None, operation=SetOperation.UNION
    )
    combined.set_block_name("missing_ref")

    with pytest.raises(ValueError, match="Both neuron set references must be set"):
        combined.get_neuron_ids(circuit)


def test_combined_recursive_cycle(circuit, ref_a, ref_b):
    """Test that a recursive cycle is detected."""
    combined_x = BiophysicalCombinedNeuronSet(
        base_neuron_set=ref_a, combined_with=ref_b, operation=SetOperation.UNION
    )
    combined_x.set_block_name("combined_x")

    combined_y = BiophysicalCombinedNeuronSet(
        base_neuron_set=ref_a, combined_with=ref_b, operation=SetOperation.UNION
    )
    combined_y.set_block_name("combined_y")

    # Create cycle: x -> y -> x
    ref_x = BiophysicalNeuronSetReference(block_dict_name="neuron_sets", block_name="combined_x")
    ref_x.block = combined_x
    ref_y = BiophysicalNeuronSetReference(block_dict_name="neuron_sets", block_name="combined_y")
    ref_y.block = combined_y

    combined_x.combined_with = ref_y
    combined_y.combined_with = ref_x

    with pytest.raises(ValueError, match="Recursive loop"):
        combined_x.get_neuron_ids(circuit)


def test_combined_no_block_name(circuit, ref_a, ref_b):
    """Test that missing block name raises."""
    combined = BiophysicalCombinedNeuronSet(
        base_neuron_set=ref_a, combined_with=ref_b, operation=SetOperation.UNION
    )
    # Don't set block name

    with pytest.raises(ValueError, match="Block name must be set"):
        combined.get_neuron_ids(circuit)


# --- Population type matching ---


def test_combined_biophysical_type_matching(circuit, ref_a, ref_b):
    """Test BiophysicalCombinedNeuronSet works when both inputs are biophysical."""
    combined = BiophysicalCombinedNeuronSet(
        base_neuron_set=ref_a, combined_with=ref_b, operation=SetOperation.UNION
    )
    combined.set_block_name("bio_type_match")

    # Symbolic path (union) — should succeed
    nset_def, combined_defs = combined.get_node_set_definition(circuit)
    assert isinstance(nset_def, list)
    assert set(nset_def) == set(combined_defs.keys())

    # Resolved path — should also succeed
    nset_def_resolved, _ = combined.get_node_set_definition(circuit, force_resolve_ids=True)
    assert "node_id" in nset_def_resolved


def test_combined_biophysical_type_mismatch_symbolic(circuit):
    """Test BiophysicalCombinedNeuronSet fails in symbolic path with a virtual input."""
    # Create a virtual neuron set
    virt_nset = VirtualPopulationNeuronSet(population="POm")
    virt_nset.set_block_name("virt_pop")
    ref_virt = VirtualNeuronSetReference(block_dict_name="neuron_sets", block_name="virt_pop")
    ref_virt.block = virt_nset

    # Create a biophysical neuron set
    bio_nset = BiophysicalPopulationPredefinedNeuronSet(
        node_set="L6_BPC", population="S1nonbarrel_neurons"
    )
    bio_nset.set_block_name("bio_pop")
    ref_bio = BiophysicalNeuronSetReference(block_dict_name="neuron_sets", block_name="bio_pop")
    ref_bio.block = bio_nset

    # Combine with union (symbolic path)
    combined = BiophysicalCombinedNeuronSet(
        base_neuron_set=ref_bio, combined_with=ref_virt, operation=SetOperation.UNION
    )
    combined.set_block_name("bio_mismatch_sym")

    # Should fail in symbolic path — virtual population not valid for biophysical type
    with pytest.raises(ValueError, match="not found in circuit"):
        combined.get_node_set_definition(circuit)


def test_combined_biophysical_type_mismatch_resolved(circuit):
    """Test BiophysicalCombinedNeuronSet fails in resolved path with a virtual input."""
    # Create a virtual neuron set
    virt_nset = VirtualPopulationNeuronSet(population="POm")
    virt_nset.set_block_name("virt_pop2")
    ref_virt = VirtualNeuronSetReference(block_dict_name="neuron_sets", block_name="virt_pop2")
    ref_virt.block = virt_nset

    # Create a biophysical neuron set
    bio_nset = BiophysicalPopulationPredefinedNeuronSet(
        node_set="L6_BPC", population="S1nonbarrel_neurons"
    )
    bio_nset.set_block_name("bio_pop2")
    ref_bio = BiophysicalNeuronSetReference(block_dict_name="neuron_sets", block_name="bio_pop2")
    ref_bio.block = bio_nset

    # Combine with intersect (non-union = resolved path)
    combined = BiophysicalCombinedNeuronSet(
        base_neuron_set=ref_bio, combined_with=ref_virt, operation=SetOperation.INTERSECT
    )
    combined.set_block_name("bio_mismatch_resolve")

    # Should fail in resolved path — virtual population not valid for biophysical type
    with pytest.raises(ValueError, match="not found in circuit"):
        combined.get_node_set_definition(circuit)


# --- Nested combined ---


def test_nested_combined(circuit):
    """Test combining a combined set with another set (depth > 1)."""
    # Create base sets
    nset_a = BiophysicalPopulationPredefinedNeuronSet(
        node_set="L6_BPC", population="S1nonbarrel_neurons"
    )
    nset_a.set_block_name("nested_a")

    nset_b = BiophysicalPopulationPredefinedNeuronSet(
        node_set="L6_TPC:A", population="S1nonbarrel_neurons"
    )
    nset_b.set_block_name("nested_b")

    nset_c = BiophysicalPopulationPredefinedNeuronSet(
        node_set="Layer6", population="S1nonbarrel_neurons"
    )
    nset_c.set_block_name("nested_c")

    # Create references
    ref_a = BiophysicalNeuronSetReference(block_dict_name="neuron_sets", block_name="nested_a")
    ref_a.block = nset_a
    ref_b = BiophysicalNeuronSetReference(block_dict_name="neuron_sets", block_name="nested_b")
    ref_b.block = nset_b
    ref_c = BiophysicalNeuronSetReference(block_dict_name="neuron_sets", block_name="nested_c")
    ref_c.block = nset_c

    # Create inner combined (A union B)
    inner = BiophysicalCombinedNeuronSet(
        base_neuron_set=ref_a, combined_with=ref_b, operation=SetOperation.UNION
    )
    inner.set_block_name("inner_combined")

    # Create reference to inner
    ref_inner = BiophysicalNeuronSetReference(
        block_dict_name="neuron_sets", block_name="inner_combined"
    )
    ref_inner.block = inner

    # Create outer combined (inner intersect C)
    outer = BiophysicalCombinedNeuronSet(
        base_neuron_set=ref_inner, combined_with=ref_c, operation=SetOperation.INTERSECT
    )
    outer.set_block_name("outer_combined")

    # (A union B) intersect C = [1, 2, 6, 7, 8, 9]
    ids_a = set(nset_a.get_neuron_ids(circuit)["S1nonbarrel_neurons"])
    ids_b = set(nset_b.get_neuron_ids(circuit)["S1nonbarrel_neurons"])
    ids_c = set(nset_c.get_neuron_ids(circuit)["S1nonbarrel_neurons"])
    expected = sorted((ids_a | ids_b) & ids_c)

    result = outer.get_neuron_ids(circuit)
    assert sorted(result["S1nonbarrel_neurons"]) == expected

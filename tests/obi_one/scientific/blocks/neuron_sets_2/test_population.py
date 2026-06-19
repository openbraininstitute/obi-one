"""Tests for neuron_sets_2 population neuron sets."""

import numpy as np
import pytest
from obi_one.scientific.blocks.neuron_sets_2.population import (
    BiophysicalPopulationNeuronSet,
    VirtualPopulationNeuronSet,
)

import obi_one as obi

from tests.utils import CIRCUIT_DIR, MATRIX_DIR

CIRCUIT_NAME = "N_10__top_nodes_dim6"


@pytest.fixture
def circuit():
    return obi.Circuit(
        name=CIRCUIT_NAME,
        path=str(CIRCUIT_DIR / CIRCUIT_NAME / "circuit_config.json"),
        matrix_path=str(MATRIX_DIR / CIRCUIT_NAME / "connectivity_matrix.h5"),
    )


def test_population_neuron_set_full(circuit):
    """Test BiophysicalPopulationNeuronSet returns all neurons without sampling."""
    nset = BiophysicalPopulationNeuronSet(population="S1nonbarrel_neurons")
    nset.set_block_name("pop_full")

    ids = nset.get_neuron_ids(circuit)
    assert "S1nonbarrel_neurons" in ids
    assert len(ids["S1nonbarrel_neurons"]) == 10

    # Symbolic expression (no sampling)
    nset_def, combined = nset.get_node_set_definition(circuit)
    assert nset_def == {"population": "S1nonbarrel_neurons"}
    assert combined == {}


def test_population_neuron_set_sampling(circuit):
    """Test BiophysicalPopulationNeuronSet with 50% sampling."""
    nset = BiophysicalPopulationNeuronSet(
        population="S1nonbarrel_neurons", sample_percentage=50, sample_seed=1
    )
    nset.set_block_name("pop_50")

    ids = nset.get_neuron_ids(circuit)
    assert len(ids["S1nonbarrel_neurons"]) == 5

    # Resolved expression (sampling active)
    nset_def, _ = nset.get_node_set_definition(circuit)
    assert nset_def["population"] == "S1nonbarrel_neurons"
    assert "node_id" in nset_def
    assert len(nset_def["node_id"]) == 5


def test_population_neuron_set_force_resolve(circuit):
    """Test force_resolve_ids returns explicit IDs even without sampling."""
    nset = BiophysicalPopulationNeuronSet(population="S1nonbarrel_neurons")
    nset.set_block_name("pop_resolve")

    nset_def, _ = nset.get_node_set_definition(circuit, force_resolve_ids=True)
    assert nset_def["population"] == "S1nonbarrel_neurons"
    assert "node_id" in nset_def
    assert len(nset_def["node_id"]) == 10


def test_population_neuron_set_invalid_population(circuit):
    """Test that an invalid population raises."""
    nset = BiophysicalPopulationNeuronSet(population="NONEXISTENT")
    nset.set_block_name("invalid_pop")

    with pytest.raises(ValueError, match="not found in circuit"):
        nset.get_neuron_ids(circuit)


def test_population_neuron_set_get_populations(circuit):
    """Test get_populations returns the single population."""
    nset = BiophysicalPopulationNeuronSet(population="S1nonbarrel_neurons")
    nset.set_block_name("pop_test")

    pops = nset.get_populations(circuit)
    assert pops == ["S1nonbarrel_neurons"]


def test_population_neuron_set_deterministic_sampling(circuit):
    """Test that same seed produces same results."""
    nset1 = BiophysicalPopulationNeuronSet(
        population="S1nonbarrel_neurons", sample_percentage=50, sample_seed=42
    )
    nset1.set_block_name("pop_det1")
    nset2 = BiophysicalPopulationNeuronSet(
        population="S1nonbarrel_neurons", sample_percentage=50, sample_seed=42
    )
    nset2.set_block_name("pop_det2")

    ids1 = nset1.get_neuron_ids(circuit)
    ids2 = nset2.get_neuron_ids(circuit)
    np.testing.assert_array_equal(ids1["S1nonbarrel_neurons"], ids2["S1nonbarrel_neurons"])


def test_population_neuron_set_different_seeds(circuit):
    """Test that different seeds produce different results."""
    nset1 = BiophysicalPopulationNeuronSet(
        population="S1nonbarrel_neurons", sample_percentage=50, sample_seed=1
    )
    nset1.set_block_name("pop_s1")
    nset2 = BiophysicalPopulationNeuronSet(
        population="S1nonbarrel_neurons", sample_percentage=50, sample_seed=2
    )
    nset2.set_block_name("pop_s2")

    ids1 = nset1.get_neuron_ids(circuit)
    ids2 = nset2.get_neuron_ids(circuit)
    # With 10 neurons and 50% sampling, different seeds should (very likely) give different results
    assert ids1["S1nonbarrel_neurons"] != ids2["S1nonbarrel_neurons"]


# --- Population type matching ---


def test_biophysical_population_matching(circuit):
    """Test that a biophysical population neuron set works with a biophysical population."""
    nset = BiophysicalPopulationNeuronSet(population="S1nonbarrel_neurons")
    nset.set_block_name("bio_match")

    ids = nset.get_neuron_ids(circuit)
    assert len(ids["S1nonbarrel_neurons"]) == 10


def test_virtual_population_mismatch(circuit):
    """Test that a virtual population neuron set fails with a biophysical population."""
    # S1nonbarrel_neurons is biophysical, not virtual -> should raise
    nset = VirtualPopulationNeuronSet(population="S1nonbarrel_neurons")
    nset.set_block_name("virt_mismatch")

    with pytest.raises(ValueError, match="not found in circuit"):
        nset.get_neuron_ids(circuit)

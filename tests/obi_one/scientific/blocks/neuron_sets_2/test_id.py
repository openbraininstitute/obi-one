"""Tests for neuron_sets_2 ID neuron sets."""

import numpy as np
import pytest

import obi_one as obi
from obi_one.core.tuple import NamedTuple
from obi_one.scientific.blocks.neuron_sets_2.id import (
    BiophysicalIDNeuronSet,
    VirtualIDNeuronSet,
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


def test_id_neuron_set_basic(circuit):
    """Test BiophysicalIDNeuronSet returns the specified IDs."""
    nset = BiophysicalIDNeuronSet(
        population="S1nonbarrel_neurons",
        neuron_ids=NamedTuple(name="test_ids", elements=(0, 2, 5, 8)),
    )
    nset.set_block_name("id_basic")

    ids = nset.get_neuron_ids(circuit)
    assert "S1nonbarrel_neurons" in ids
    np.testing.assert_array_equal(sorted(ids["S1nonbarrel_neurons"]), [0, 2, 5, 8])


def test_id_neuron_set_expression(circuit):
    """Test BiophysicalIDNeuronSet node set definition contains population and node_id."""
    nset = BiophysicalIDNeuronSet(
        population="S1nonbarrel_neurons",
        neuron_ids=NamedTuple(name="test_ids", elements=(1, 3, 7)),
    )
    nset.set_block_name("id_expr")

    nset_def, combined = nset.get_node_set_definition(circuit)
    assert nset_def["population"] == "S1nonbarrel_neurons"
    assert nset_def["node_id"] == [1, 3, 7]
    assert combined == {}


def test_id_neuron_set_with_sampling(circuit):
    """Test BiophysicalIDNeuronSet with sub-sampling."""
    nset = BiophysicalIDNeuronSet(
        population="S1nonbarrel_neurons",
        neuron_ids=NamedTuple(name="test_ids", elements=list(range(10))),
        sample_percentage=50,
        sample_seed=1,
    )
    nset.set_block_name("id_sampled")

    ids = nset.get_neuron_ids(circuit)
    assert len(ids["S1nonbarrel_neurons"]) == 5


def test_id_neuron_set_invalid_ids(circuit):
    """Test that neuron IDs not in the population raise an error."""
    nset = BiophysicalIDNeuronSet(
        population="S1nonbarrel_neurons",
        neuron_ids=NamedTuple(name="bad_ids", elements=(0, 999)),
    )
    nset.set_block_name("id_invalid")

    with pytest.raises(ValueError, match="Neuron ID"):
        nset.get_neuron_ids(circuit)


def test_id_neuron_set_biophysical_matching(circuit):
    """Test BiophysicalIDNeuronSet works with biophysical population."""
    nset = BiophysicalIDNeuronSet(
        population="S1nonbarrel_neurons",
        neuron_ids=NamedTuple(name="bio_ids", elements=(0, 1, 2)),
    )
    nset.set_block_name("id_bio")

    ids = nset.get_neuron_ids(circuit)
    np.testing.assert_array_equal(sorted(ids["S1nonbarrel_neurons"]), [0, 1, 2])


def test_id_neuron_set_virtual_mismatch(circuit):
    """Test VirtualIDNeuronSet fails with a biophysical population."""
    nset = VirtualIDNeuronSet(
        population="S1nonbarrel_neurons",
        neuron_ids=NamedTuple(name="virt_ids", elements=(0, 1)),
    )
    nset.set_block_name("id_virt_mismatch")

    with pytest.raises(ValueError, match="not found in circuit"):
        nset.get_neuron_ids(circuit)

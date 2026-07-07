"""Tests for neuron_sets specific neuron sets."""

import pytest

import obi_one as obi
from obi_one.scientific.blocks.neuron_sets.specific import (
    AllBiophysicalNeurons,
    AllNonVirtualNeurons,
    AllPointNeurons,
    AllPopulationNeurons,
    AllVirtualNeurons,
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


def test_all_population_neurons(circuit):
    """Test AllPopulationNeurons returns all populations and IDs."""
    nset = AllPopulationNeurons()
    nset.set_block_name("all")

    pops = nset.get_populations(circuit)
    assert len(pops) >= 1
    assert "S1nonbarrel_neurons" in pops

    ids = nset.get_neuron_ids(circuit)
    # Should have IDs from all populations
    total = sum(len(v) for v in ids.values())
    assert total > 0


def test_all_population_neurons_symbolic(circuit):
    """Test AllPopulationNeurons symbolic node set definition."""
    nset = AllPopulationNeurons()
    nset.set_block_name("all_sym")

    nset_def, combined = nset.get_node_set_definition(circuit)
    pops = nset.get_populations(circuit)
    # Test circuit has multiple populations -> compound expression
    assert isinstance(nset_def, list)
    assert len(nset_def) == len(pops)
    assert len(combined) == len(pops)


def test_all_population_neurons_force_resolve(circuit):
    """Test AllPopulationNeurons force_resolve_ids."""
    nset = AllPopulationNeurons()
    nset.set_block_name("all_resolve")

    nset_def, combined = nset.get_node_set_definition(circuit, force_resolve_ids=True)
    pops = nset.get_populations(circuit)
    # Multiple populations -> compound expression with node_id in each entry
    assert isinstance(nset_def, list)
    assert len(nset_def) == len(pops)
    for key in nset_def:
        assert "node_id" in combined[key]


def test_all_biophysical_neurons(circuit):
    """Test AllBiophysicalNeurons returns only biophysical populations."""
    nset = AllBiophysicalNeurons()
    nset.set_block_name("all_bio")

    pops = nset.get_populations(circuit)
    assert "S1nonbarrel_neurons" in pops

    ids = nset.get_neuron_ids(circuit)
    assert "S1nonbarrel_neurons" in ids
    assert len(ids["S1nonbarrel_neurons"]) == 10


def test_all_virtual_neurons(circuit):
    """Test AllVirtualNeurons returns only virtual populations."""
    nset = AllVirtualNeurons()
    nset.set_block_name("all_virt")

    pops = nset.get_populations(circuit)
    # Should not include biophysical population
    assert "S1nonbarrel_neurons" not in pops

    ids = nset.get_neuron_ids(circuit)
    # Virtual populations should have neurons
    assert all(isinstance(v, list) for v in ids.values())


def test_all_non_virtual_neurons(circuit):
    """Test AllNonVirtualNeurons includes biophysical but not virtual."""
    nset = AllNonVirtualNeurons()
    nset.set_block_name("all_nonvirt")

    pops = nset.get_populations(circuit)
    assert "S1nonbarrel_neurons" in pops

    # Virtual populations should not be included
    virt_nset = AllVirtualNeurons()
    virt_nset.set_block_name("virt_check")
    virt_pops = virt_nset.get_populations(circuit)
    for vp in virt_pops:
        assert vp not in pops


def test_all_point_neurons(circuit):
    """Test AllPointNeurons returns only point populations."""
    nset = AllPointNeurons()
    nset.set_block_name("all_point")

    pops = nset.get_populations(circuit)
    # Biophysical population should not be included
    assert "S1nonbarrel_neurons" not in pops


def test_all_population_neurons_no_block_name(circuit):
    """Test that get_node_set_definition raises without block name."""
    nset = AllPopulationNeurons()

    with pytest.raises(ValueError, match="Block name must be set"):
        nset.get_node_set_definition(circuit)

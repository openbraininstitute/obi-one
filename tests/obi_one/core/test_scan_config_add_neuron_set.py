"""Tests for ScanConfig.add() with neuron set blocks.

Verifies that adding neuron set blocks correctly resolves the appropriate
BlockReference type from the registry based on the block's class.
"""

import pytest

import obi_one as obi
from obi_one.core.exception import OBIONEError
from obi_one.core.scan_config import _reference_type_name_for_block
from obi_one.scientific.blocks.neuron_sets.id import (
    BiophysicalPopulationIDNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.population import (
    BiophysicalPopulationNeuronSet,
    VirtualPopulationNeuronSet,
)
from obi_one.scientific.unions_and_references.neuron_sets import (
    BiophysicalNeuronSetReference,
    VirtualNeuronSetReference,
)


@pytest.fixture
def sim_conf():
    return obi.CircuitSimulationScanConfig.empty_config()


def test_add_biophysical_neuron_set(sim_conf):
    """Adding a biophysical neuron set resolves to BiophysicalNeuronSetReference."""
    nset = BiophysicalPopulationIDNeuronSet(
        neuron_ids=obi.NamedTuple(name="ids", elements=(0, 1, 2)),
        population="pop_A",
    )
    sim_conf.add(nset, name="bio_nset")

    assert "bio_nset" in sim_conf.neuron_sets
    assert sim_conf.neuron_sets["bio_nset"] is nset
    assert nset.has_block_name()
    assert nset.block_name == "bio_nset"
    # Check that the reference is the correct type
    ref = nset.ref
    assert isinstance(ref, BiophysicalNeuronSetReference)
    assert ref.block_name == "bio_nset"


def test_add_virtual_neuron_set(sim_conf):
    """Adding a virtual neuron set resolves to VirtualNeuronSetReference."""
    nset = VirtualPopulationNeuronSet(population="virt_pop")
    sim_conf.add(nset, name="virt_nset")

    assert "virt_nset" in sim_conf.neuron_sets
    ref = nset.ref
    assert isinstance(ref, VirtualNeuronSetReference)


def test_add_multiple_neuron_sets_different_types(sim_conf):
    """Adding neuron sets of different types resolves each to the correct reference."""
    bio = BiophysicalPopulationNeuronSet(population="pop_bio")
    virt = VirtualPopulationNeuronSet(population="pop_virt")

    sim_conf.add(bio, name="bio")
    sim_conf.add(virt, name="virt")

    assert isinstance(bio.ref, BiophysicalNeuronSetReference)
    assert isinstance(virt.ref, VirtualNeuronSetReference)


def test_add_duplicate_name_raises(sim_conf):
    """Adding a block with a name that already exists raises."""
    nset1 = BiophysicalPopulationNeuronSet(population="pop_A")
    nset2 = BiophysicalPopulationNeuronSet(population="pop_B")

    sim_conf.add(nset1, name="same_name")
    with pytest.raises(OBIONEError, match="already exists"):
        sim_conf.add(nset2, name="same_name")


def test_reference_type_name_matches_allowed_block():
    """Returns the reference whose allowed_block_types lists the block class."""
    result = _reference_type_name_for_block(
        "VirtualPopulationIDNeuronSet",
        ["BiophysicalNeuronSetReference", "VirtualNeuronSetReference"],
    )
    assert result == "VirtualNeuronSetReference"


def test_reference_type_name_returns_first_accepting_candidate():
    """Returns the first candidate that accepts the block, honoring order."""
    result = _reference_type_name_for_block(
        "BiophysicalPopulationIDNeuronSet",
        ["BiophysicalNeuronSetReference", "VirtualNeuronSetReference"],
    )
    assert result == "BiophysicalNeuronSetReference"


def test_reference_type_name_no_candidate_accepts_returns_none():
    """Returns None when no candidate reference accepts the block class."""
    result = _reference_type_name_for_block(
        "VirtualPopulationIDNeuronSet",
        ["BiophysicalNeuronSetReference"],
    )
    assert result is None


def test_reference_type_name_unknown_candidate_name_is_skipped():
    """A name not in the registry is skipped; a later valid candidate still matches."""
    result = _reference_type_name_for_block(
        "VirtualPopulationIDNeuronSet",
        ["NotARegisteredReference", "VirtualNeuronSetReference"],
    )
    assert result == "VirtualNeuronSetReference"


def test_reference_type_name_empty_candidates_returns_none():
    """No candidates at all returns None."""
    assert _reference_type_name_for_block("VirtualPopulationIDNeuronSet", []) is None


def test_reference_type_name_unrestricted_reference_accepts_any_block():
    """A reference with no allowed_block_types restriction accepts any block class."""
    # SynapticModelReference declares no allowed_block_types, so it accepts anything.
    result = _reference_type_name_for_block("AnyBlockClass", ["SynapticModelReference"])
    assert result == "SynapticModelReference"

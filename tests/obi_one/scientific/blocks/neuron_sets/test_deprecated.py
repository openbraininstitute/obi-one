"""Tests for the deprecated neuron sets.

These blocks exist so that configs written before the population-typed neuron-set taxonomy still
deserialize -- and so remain openable and editable in the UI -- while refusing to resolve against
a circuit, which forces a migration before they can be run.
"""

import operator

import pytest
from pydantic import TypeAdapter, ValidationError

import obi_one as obi
from obi_one.scientific.blocks.neuron_sets.deprecated import PredefinedNeuronSet
from obi_one.scientific.unions_and_references.neuron_sets import (
    AtomicBiophysicalNeuronSetUnion,
    AtomicPointNeuronSetUnion,
    AtomicVirtualNeuronSetUnion,
)

from tests.utils import CIRCUIT_DIR, MATRIX_DIR

CIRCUIT_NAME = "N_10__top_nodes_dim6"

# A neuron set exactly as stored by simulation configs written before the population-typed
# taxonomy: no `population`, and the sampling fields that the current PredefinedNeuronSet
# (now MultiPopulationPredefinedNeuronSet) no longer carries.
LEGACY_PREDEFINED_NEURON_SET = {
    "type": "PredefinedNeuronSet",
    "node_set": "Layer6",
    "sample_percentage": 100.0,
    "sample_seed": 1,
}


@pytest.fixture
def circuit():
    return obi.Circuit(
        name=CIRCUIT_NAME,
        path=str(CIRCUIT_DIR / CIRCUIT_NAME / "circuit_config.json"),
        matrix_path=str(MATRIX_DIR / CIRCUIT_NAME / "connectivity_matrix.h5"),
    )


def test_legacy_predefined_neuron_set_deserializes():
    """A legacy PredefinedNeuronSet block still loads, fields and all."""
    nset = PredefinedNeuronSet.model_validate(LEGACY_PREDEFINED_NEURON_SET)

    assert nset.node_set == "Layer6"
    assert nset.sample_percentage == pytest.approx(100.0)
    assert nset.sample_seed == 1


DEPRECATED_NEURON_SETS = [
    LEGACY_PREDEFINED_NEURON_SET,
    {"type": "AllNeurons", "sample_percentage": 100.0, "sample_seed": 1},
    {"type": "ExcitatoryNeurons", "sample_percentage": 100.0, "sample_seed": 1},
    {"type": "InhibitoryNeurons", "sample_percentage": 100.0, "sample_seed": 1},
    {"type": "IDNeuronSet", "neuron_ids": {"name": "ids", "elements": [1, 2]}},
    {"type": "nbS1VPMInputs", "sample_percentage": 100.0, "sample_seed": 1},
    {"type": "nbS1POmInputs", "sample_percentage": 100.0, "sample_seed": 1},
    {"type": "rCA1CA3Inputs", "sample_percentage": 100.0, "sample_seed": 1},
]


@pytest.mark.parametrize(
    "union",
    [AtomicBiophysicalNeuronSetUnion, AtomicVirtualNeuronSetUnion],
    ids=["biophysical", "virtual"],
)
@pytest.mark.parametrize("block", DEPRECATED_NEURON_SETS, ids=operator.itemgetter("type"))
def test_deprecated_neuron_sets_resolve_through_biophysical_and_virtual_unions(block, union):
    """Every deprecated neuron set resolves through the biophysical and virtual unions.

    That is what a stored config is validated by; without it, loading one fails with
    `union_tag_invalid` and the UI has no schema definition to render the block with.

    Both population types for every block, because the deprecated sets predate the
    population-typed taxonomy -- a neuron set carried no population type then -- so configs
    written before the rework use them in either slot, regardless of the type the class
    nominally declares now. In the wild: AllNeurons (nominally biophysical) selecting the
    virtual input population of an ME-model-with-synapses simulation.
    """
    nset = TypeAdapter(union).validate_python(block)

    assert nset.type == block["type"]


@pytest.mark.parametrize("block", DEPRECATED_NEURON_SETS, ids=operator.itemgetter("type"))
def test_deprecated_neuron_sets_are_not_offered_for_point_populations(block):
    """No deprecated neuron set is accepted for a point population.

    Point-neuron support was introduced by the same rework that deprecated them, so no config
    predating the rework can target a point population and these blocks have no meaning for one.
    """
    with pytest.raises(ValidationError):
        TypeAdapter(AtomicPointNeuronSetUnion).validate_python(block)


def test_legacy_predefined_neuron_set_is_in_the_schema():
    """The block has a definition in the schema the frontend binds stored configs against."""
    schema = obi.CircuitSimulationScanConfig.model_json_schema()

    assert "PredefinedNeuronSet" in schema["$defs"]


def test_legacy_predefined_neuron_set_cannot_be_resolved(circuit):
    """Being deprecated, it refuses to resolve: the config must be migrated before it runs."""
    nset = PredefinedNeuronSet.model_validate(LEGACY_PREDEFINED_NEURON_SET)

    with pytest.raises(NotImplementedError, match="deprecated"):
        nset.get_neuron_ids(circuit)

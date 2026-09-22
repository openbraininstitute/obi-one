from collections import UserDict
from types import SimpleNamespace

import pytest
from pydantic import Field

from obi_one.scientific.blocks.neuron_sets.population import (
    BiophysicalPopulationNeuronSet,
)
from obi_one.scientific.blocks.synaptic_model_assigners.all_pairs import (
    AllPairsSynapticModelAssigner,
)
from obi_one.scientific.blocks.synaptic_model_assigners.inter_neuron_set import (
    InterNeuronSetSynapticModelAssigner,
)
from obi_one.scientific.blocks.synaptic_model_assigners.presyn_neuron_set import (
    PresynapticNeuronSetSynapticModelAssigner,
)
from obi_one.scientific.unions_and_references.neuron_sets import BiophysicalNeuronSetReference


class _FakeEdgePopulation:
    def __init__(self, name, source, target):
        self.name = name
        self.source = SimpleNamespace(name=source)
        self.target = SimpleNamespace(name=target)


class _FakeEdges(UserDict):
    @property
    def population_names(self):
        return list(self)


def _circuit(edge_populations=(("default", "excitatory", "inhibitory"),)):
    edges = _FakeEdges(
        {name: _FakeEdgePopulation(name, src, tgt) for name, src, tgt in edge_populations}
    )
    return SimpleNamespace(sonata_circuit=SimpleNamespace(edges=edges))


class _NeuronSetSpanning(BiophysicalPopulationNeuronSet):
    """A neuron set standing in for one that resolves in several node populations.

    `get_populations` is what the validation reads, and it is the same set of names
    `get_neuron_ids` is keyed by - which is what `_edge_indices` then indexes. A
    predefined or combined set needs a real circuit to resolve, so this overrides the
    one method under test instead.
    """

    spans: list[str] = Field(default_factory=list)

    def get_populations(self, circuit) -> list[str]:  # ruff: ignore[unused-method-argument]
        return list(self.spans)


def _neuron_set_spanning(*populations):
    neuron_set = _NeuronSetSpanning(population=populations[0], spans=list(populations))
    neuron_set.set_block_name("test_neuron_set")
    reference = BiophysicalNeuronSetReference(
        block_dict_name="neuron_sets", block_name="test_neuron_set"
    )
    reference.block = neuron_set
    return reference


def _inter(**kwargs):
    return InterNeuronSetSynapticModelAssigner(edge_population_name="default", **kwargs)


def test_unknown_edge_population_is_named_along_with_the_alternatives():
    assigner = AllPairsSynapticModelAssigner(edge_population_name="typo")

    with pytest.raises(ValueError, match="not in this circuit") as exc_info:
        assigner.validate_for_circuit(_circuit())

    assert "typo" in str(exc_info.value)
    assert "default" in str(exc_info.value)


def test_all_pairs_accepts_a_population_that_exists():
    AllPairsSynapticModelAssigner(edge_population_name="default").validate_for_circuit(_circuit())


def test_source_neuron_set_on_the_wrong_population_is_rejected():
    # The case this exists for: the edge population carries no synapse that starts at
    # these neurons, which used to be a KeyError from inside _edge_indices mid-run.
    assigner = _inter(
        source_neuron_set=_neuron_set_spanning("some_other_population"),
        targeted_neuron_set=_neuron_set_spanning("inhibitory"),
    )

    with pytest.raises(ValueError, match="source population 'excitatory'"):
        assigner.validate_for_circuit(_circuit())


def test_target_neuron_set_on_the_wrong_population_is_rejected():
    assigner = _inter(
        source_neuron_set=_neuron_set_spanning("excitatory"),
        targeted_neuron_set=_neuron_set_spanning("some_other_population"),
    )

    with pytest.raises(ValueError, match="target population 'inhibitory'"):
        assigner.validate_for_circuit(_circuit())


def test_matching_neuron_sets_are_accepted():
    _inter(
        source_neuron_set=_neuron_set_spanning("excitatory"),
        targeted_neuron_set=_neuron_set_spanning("inhibitory"),
    ).validate_for_circuit(_circuit())


def test_a_neuron_set_spanning_several_populations_only_has_to_include_the_right_one():
    # A predefined or combined neuron set resolves in several populations; covering the
    # edge population's end is enough, because get_neuron_ids is keyed by all of them.
    _inter(
        source_neuron_set=_neuron_set_spanning("virtual", "excitatory"),
        targeted_neuron_set=_neuron_set_spanning("inhibitory", "excitatory"),
    ).validate_for_circuit(_circuit())


@pytest.mark.parametrize("missing", ["source_neuron_set", "targeted_neuron_set"])
def test_a_missing_neuron_set_is_rejected(missing):
    neuron_sets = {
        "source_neuron_set": _neuron_set_spanning("excitatory"),
        "targeted_neuron_set": _neuron_set_spanning("inhibitory"),
    }
    neuron_sets[missing] = None

    with pytest.raises(ValueError, match="is required"):
        _inter(**neuron_sets).validate_for_circuit(_circuit())


def test_presynaptic_assigner_checks_only_its_source():
    assigner = PresynapticNeuronSetSynapticModelAssigner(
        edge_population_name="default",
        source_neuron_set=_neuron_set_spanning("excitatory"),
    )

    assigner.validate_for_circuit(_circuit())

    mismatched = PresynapticNeuronSetSynapticModelAssigner(
        edge_population_name="default",
        source_neuron_set=_neuron_set_spanning("inhibitory"),
    )
    with pytest.raises(ValueError, match="source population 'excitatory'"):
        mismatched.validate_for_circuit(_circuit())

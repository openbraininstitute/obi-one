from collections import UserDict
from types import SimpleNamespace
from typing import ClassVar

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
from obi_one.scientific.blocks.synaptic_models.base import SynapseModelFamily, SynapticModelBase
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram.block import (
    ExcitatoryTsodyksMarkramSynapticModel,
)
from obi_one.scientific.unions_and_references.neuron_sets import BiophysicalNeuronSetReference
from obi_one.scientific.unions_and_references.synaptic_models import SynapticModelReference


class _Exp2SynLikeModel(SynapticModelBase):
    """A stand-in for a future, non-Tsodyks-Markram synapse model.

    Exists to prove the compatibility check is driven by whatever the assigned model
    declares rather than by a fixed list of types - a model for an "Exp2Syn_synapse"
    population must be accepted there and rejected on "chemical".
    """

    _synapse_model_family: ClassVar[SynapseModelFamily] = SynapseModelFamily.TSODYKS_MARKRAM
    _compatible_edge_population_types: ClassVar[tuple[str, ...]] = ("Exp2Syn_synapse",)

    @property
    def syn_type_id(self) -> int:
        return 100


def _model_reference(model):
    reference = SynapticModelReference(block_dict_name="synaptic_models", block_name="test_model")
    reference.block = model
    return reference


class _FakeEdgePopulation:
    def __init__(self, name, source, target, edge_type="chemical"):
        self.name = name
        self.source = SimpleNamespace(name=source)
        self.target = SimpleNamespace(name=target)
        self.type = edge_type


class _FakeEdges(UserDict):
    @property
    def population_names(self):
        return list(self)


def _circuit(edge_populations=(("default", "excitatory", "inhibitory"),)):
    # Each entry is (name, source, target) or (name, source, target, edge_type); the
    # edge type defaults to "chemical" so callers that only care about populations and
    # neuron sets stay unaffected by the chemical-only check.
    edges = _FakeEdges({entry[0]: _FakeEdgePopulation(*entry) for entry in edge_populations})
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
    kwargs.setdefault("synaptic_model", _model_reference(ExcitatoryTsodyksMarkramSynapticModel()))
    return InterNeuronSetSynapticModelAssigner(edge_population_name="default", **kwargs)


def test_unknown_edge_population_is_named_along_with_the_alternatives():
    assigner = AllPairsSynapticModelAssigner(edge_population_name="typo")

    with pytest.raises(ValueError, match="not in this circuit") as exc_info:
        assigner.validate_for_circuit(_circuit())

    assert "typo" in str(exc_info.value)
    assert "default" in str(exc_info.value)


def test_all_pairs_accepts_a_population_that_exists():
    AllPairsSynapticModelAssigner(
        edge_population_name="default",
        synaptic_model=_model_reference(ExcitatoryTsodyksMarkramSynapticModel()),
    ).validate_for_circuit(_circuit())


def test_electrical_edge_population_is_rejected_for_a_chemical_only_model():
    # A Tsodyks-Markram model describes chemical transmission, so an electrical (gap
    # junction) population has no mechanism for the parameters it would write.
    circuit = _circuit(
        edge_populations=(("gap_junctions", "excitatory", "excitatory", "electrical"),)
    )
    assigner = AllPairsSynapticModelAssigner(
        edge_population_name="gap_junctions",
        synaptic_model=_model_reference(ExcitatoryTsodyksMarkramSynapticModel()),
    )

    with pytest.raises(ValueError, match="can only be assigned") as exc_info:
        assigner.validate_for_circuit(circuit)

    assert "electrical" in str(exc_info.value)
    assert "gap_junctions" in str(exc_info.value)


def test_a_synapse_model_family_with_different_parameters_is_rejected_on_chemical():
    # Exp2Syn_synapse and chemical populations carry unrelated parameter sets, so a model
    # declared for one must be rejected on the other even though both are "chemical-ish".
    circuit = _circuit(edge_populations=(("default", "excitatory", "inhibitory", "chemical"),))
    assigner = AllPairsSynapticModelAssigner(
        edge_population_name="default",
        synaptic_model=_model_reference(_Exp2SynLikeModel()),
    )

    with pytest.raises(ValueError, match="can only be assigned"):
        assigner.validate_for_circuit(circuit)


def test_a_synapse_model_is_accepted_on_the_type_it_declares():
    # The mirror image of the previous test: the same model is accepted on the type it
    # actually declares, proving the check is driven by the model, not a fixed list.
    circuit = _circuit(
        edge_populations=(("default", "excitatory", "inhibitory", "Exp2Syn_synapse"),)
    )
    AllPairsSynapticModelAssigner(
        edge_population_name="default",
        synaptic_model=_model_reference(_Exp2SynLikeModel()),
    ).validate_for_circuit(circuit)


def test_an_unresolved_synaptic_model_is_rejected():
    # By the time a SingleConfig reaches the task, fill_none_references has already
    # substituted every unset synaptic_model with its tag's default. A None here means
    # that fill never ran, which create_parameters would otherwise turn into a bare
    # AttributeError on None.block deep inside execute().
    assigner = AllPairsSynapticModelAssigner(edge_population_name="default")

    with pytest.raises(ValueError, match="no synaptic model resolved"):
        assigner.validate_for_circuit(_circuit())


def test_edge_type_is_checked_before_neuron_set_spans():
    # An electrical population with mismatched neuron sets should report the type problem,
    # since the base check runs before the subclass probes the population's endpoints.
    circuit = _circuit(
        edge_populations=(("gap_junctions", "excitatory", "inhibitory", "electrical"),)
    )
    assigner = InterNeuronSetSynapticModelAssigner(
        edge_population_name="gap_junctions",
        synaptic_model=_model_reference(ExcitatoryTsodyksMarkramSynapticModel()),
        source_neuron_set=_neuron_set_spanning("some_other_population"),
        targeted_neuron_set=_neuron_set_spanning("some_other_population"),
    )

    with pytest.raises(ValueError, match="can only be assigned"):
        assigner.validate_for_circuit(circuit)


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
        synaptic_model=_model_reference(ExcitatoryTsodyksMarkramSynapticModel()),
        source_neuron_set=_neuron_set_spanning("excitatory"),
    )

    assigner.validate_for_circuit(_circuit())

    mismatched = PresynapticNeuronSetSynapticModelAssigner(
        edge_population_name="default",
        synaptic_model=_model_reference(ExcitatoryTsodyksMarkramSynapticModel()),
        source_neuron_set=_neuron_set_spanning("inhibitory"),
    )
    with pytest.raises(ValueError, match="source population 'excitatory'"):
        mismatched.validate_for_circuit(_circuit())

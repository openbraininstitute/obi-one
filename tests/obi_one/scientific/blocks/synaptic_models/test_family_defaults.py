import pytest

from obi_one.scientific.blocks.synaptic_models.base import (
    SynapseModelFamily,
    SynapticModelBase,
)
from obi_one.scientific.blocks.synaptic_models.family_defaults import (
    DEFAULT_SYNAPTIC_MODELS,
    default_synaptic_model_for,
)
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    ExcitatoryTsodyksMarkramSynapticModel,
    InhibitoryTsodyksMarkramSynapticModel,
    TsodyksMarkramSynapticModel,
)


@pytest.mark.parametrize(
    "model_class",
    [
        TsodyksMarkramSynapticModel,
        ExcitatoryTsodyksMarkramSynapticModel,
        InhibitoryTsodyksMarkramSynapticModel,
    ],
)
def test_synapse_model_family_is_the_declared_member(model_class):
    # Guards the ClassVar declaration: declared as a bare annotated underscore attribute,
    # pydantic hands back a ModelPrivateAttr here, which silently breaks every family lookup.
    assert model_class.synapse_model_family() is SynapseModelFamily.TSODYKS_MARKRAM


def test_family_without_a_declared_name_is_rejected():
    class FamilylessSynapticModel(SynapticModelBase):
        pass

    with pytest.raises(NotImplementedError, match="_synapse_model_family"):
        FamilylessSynapticModel.synapse_model_family()


@pytest.mark.parametrize(
    "model_class",
    [ExcitatoryTsodyksMarkramSynapticModel, InhibitoryTsodyksMarkramSynapticModel],
)
def test_tsodyks_markram_default_is_excitatory(model_class):
    # The point of the registry: an inhibitory model configured by the user still resolves
    # to the excitatory default, because the default parameterizes the synapses nobody claimed.
    assert isinstance(
        default_synaptic_model_for(model_class()), ExcitatoryTsodyksMarkramSynapticModel
    )


def test_default_is_a_fresh_instance_each_call():
    first = default_synaptic_model_for(ExcitatoryTsodyksMarkramSynapticModel())
    second = default_synaptic_model_for(ExcitatoryTsodyksMarkramSynapticModel())
    assert first is not second


def test_default_provides_the_family_parameters():
    default = default_synaptic_model_for(InhibitoryTsodyksMarkramSynapticModel())
    assert default.parameter_names() == InhibitoryTsodyksMarkramSynapticModel.parameter_names()


def test_every_family_has_a_default():
    # What the closed enum buys: a family added without a default fails here rather than
    # partway through parameterizing a circuit.
    assert set(DEFAULT_SYNAPTIC_MODELS) == set(SynapseModelFamily)


def test_every_registered_default_belongs_to_the_family_it_is_registered_for():
    for family, default_class in DEFAULT_SYNAPTIC_MODELS.items():
        assert default_class.synapse_model_family() is family


def test_family_without_a_registered_default_raises(monkeypatch):
    monkeypatch.delitem(DEFAULT_SYNAPTIC_MODELS, SynapseModelFamily.TSODYKS_MARKRAM)

    with pytest.raises(NotImplementedError, match=SynapseModelFamily.TSODYKS_MARKRAM.value):
        default_synaptic_model_for(ExcitatoryTsodyksMarkramSynapticModel())

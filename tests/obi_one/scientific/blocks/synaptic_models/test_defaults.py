from typing import ClassVar

import pytest

from obi_one.scientific.blocks.synaptic_models.base import SynapticModelBase
from obi_one.scientific.blocks.synaptic_models.defaults import (
    DEFAULT_SYNAPTIC_MODELS,
    default_synaptic_model_for,
)
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    ExcitatoryTsodyksMarkramSynapticModel,
    InhibitoryTsodyksMarkramSynapticModel,
    TsodyksMarkramSynapticModel,
)


def test_synapse_model_family_is_the_declared_string():
    # Guards the ClassVar declaration: a bare `_synapse_model_family = "TM_model"` makes
    # pydantic hand back a ModelPrivateAttr here, which silently breaks every family lookup.
    assert TsodyksMarkramSynapticModel.synapse_model_family() == "TM_model"
    assert ExcitatoryTsodyksMarkramSynapticModel.synapse_model_family() == "TM_model"
    assert InhibitoryTsodyksMarkramSynapticModel.synapse_model_family() == "TM_model"


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


def test_unregistered_family_raises():
    class OtherFamilySynapticModel(SynapticModelBase):
        _synapse_model_family: ClassVar[str] = "not_a_registered_family"

    with pytest.raises(NotImplementedError, match="not_a_registered_family"):
        default_synaptic_model_for(OtherFamilySynapticModel())


def test_every_registered_default_belongs_to_the_family_it_is_registered_for():
    for family, default_class in DEFAULT_SYNAPTIC_MODELS.items():
        assert default_class.synapse_model_family() == family

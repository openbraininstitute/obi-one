import pytest

from obi_one.scientific.blocks.synaptic_models.base import SynapticModelBase
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    ExcitatoryTsodyksMarkramSynapticModel,
    InhibitoryTsodyksMarkramSynapticModel,
)


def test_excitatory_model_names_the_ampa_nmda_mechanism():
    assert ExcitatoryTsodyksMarkramSynapticModel.mod_file_names() == ("ProbAMPANMDA_EMS.mod",)


def test_inhibitory_model_names_the_gaba_mechanism():
    assert InhibitoryTsodyksMarkramSynapticModel.mod_file_names() == ("ProbGABAAB_EMS.mod",)


def test_a_model_without_mod_file_names_declared_is_rejected():
    class UndeclaredModel(SynapticModelBase):
        @property
        def syn_type_id(self) -> int:
            return 100

    with pytest.raises(NotImplementedError, match="_mod_file_names"):
        UndeclaredModel.mod_file_names()


@pytest.mark.parametrize(
    ("model_class", "expected_name"),
    [
        (ExcitatoryTsodyksMarkramSynapticModel, "ProbAMPANMDA_EMS.mod"),
        (InhibitoryTsodyksMarkramSynapticModel, "ProbGABAAB_EMS.mod"),
    ],
)
def test_copy_mod_files_writes_the_generic_file_into_an_empty_destination(
    tmp_path, model_class, expected_name
):
    model_class.copy_mod_files(tmp_path)

    copied = tmp_path / expected_name
    assert copied.exists()
    assert copied.read_text()  # not empty


def test_copy_mod_files_does_not_overwrite_a_file_already_present(tmp_path):
    # The whole point of this method: a circuit's own, possibly differently parameterized,
    # copy of a mechanism must not be silently replaced by the repo's generic version.
    existing = tmp_path / "ProbAMPANMDA_EMS.mod"
    existing.write_text("CIRCUIT SPECIFIC CONTENT")

    ExcitatoryTsodyksMarkramSynapticModel.copy_mod_files(tmp_path)

    assert existing.read_text() == "CIRCUIT SPECIFIC CONTENT"


def test_copy_mod_files_creates_only_the_files_the_model_names(tmp_path):
    ExcitatoryTsodyksMarkramSynapticModel.copy_mod_files(tmp_path)

    assert [p.name for p in tmp_path.iterdir()] == ["ProbAMPANMDA_EMS.mod"]

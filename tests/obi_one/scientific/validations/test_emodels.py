from pathlib import Path

import pytest

from obi_one.scientific.validations.emodels import check_mechanisms, check_structure

DATA_FOLDER_PATH = Path(__file__).parent.parent.parent.parent / "test_data"
GOOD_HOC_TEMPLATE_PATH = DATA_FOLDER_PATH / "cADpyr.hoc"
BAD_HOC_TEMPLATE_PATH = DATA_FOLDER_PATH / "createsimulation.hoc"  # not a hoc template


def test_check_structure():
    check_structure(GOOD_HOC_TEMPLATE_PATH)  # should run without raising any error

    with pytest.raises(AssertionError):
        check_structure(BAD_HOC_TEMPLATE_PATH)


def test_check_mechanisms():
    # pas is neuron builtin so it won't be in the expected suffixes (list of mod files suffixes)
    # even though it is inserteed in the hoc file
    expected_suffixes = {
        "Ih",
        "Nap_Et2",
        "NaTg",
        "CaDynamics_DC0",
        "Ca_HVA2",
        "Ca_LVAst",
        "SKv3_1",
        "SK_E2",
        "K_Pst",
        "K_Tst",
    }
    check_mechanisms(GOOD_HOC_TEMPLATE_PATH, expected_suffixes=expected_suffixes)

    with pytest.raises(AssertionError):
        expected_suffixes.remove("Ih")  # removing Ih to make it incompatible with the hoc file
        check_mechanisms(GOOD_HOC_TEMPLATE_PATH, expected_suffixes=expected_suffixes)

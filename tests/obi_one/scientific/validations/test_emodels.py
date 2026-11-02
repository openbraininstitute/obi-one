"""Tests for obi_one.scientific.validations.emodels."""

from unittest.mock import MagicMock, patch

import pytest

from obi_one.scientific.validations.emodels import (
    BUILTIN_NEURON_MECHANISMS,
    bluecellulab_initializable,
    check_mechanisms,
    check_structure,
)

VALID_HOC = """\
begintemplate cADpyr_L2TPC
proc init() {
    insert pas
    insert hh
}
endtemplate cADpyr_L2TPC
"""

HOC_NO_BEGIN = """\
proc init() {
    insert pas
}
endtemplate cADpyr_L2TPC
"""

HOC_NO_END = """\
begintemplate cADpyr_L2TPC
proc init() {
    insert pas
}
"""

HOC_MISMATCHED_END = """\
begintemplate cADpyr_L2TPC
proc init() {}
endtemplate WrongName
"""

HOC_WITH_CUSTOM_MECHANISM = """\
begintemplate myCell
proc init() {
    insert NaTg
    insert pas
    insert Kv3_1
}
endtemplate myCell
"""


class TestCheckStructure:
    def test_valid_hoc(self, tmp_path):
        hoc = tmp_path / "cell.hoc"
        hoc.write_text(VALID_HOC)
        check_structure(hoc)  # should not raise

    def test_missing_begintemplate(self, tmp_path):
        hoc = tmp_path / "cell.hoc"
        hoc.write_text(HOC_NO_BEGIN)
        with pytest.raises(ValueError, match="begintemplate"):
            check_structure(hoc)

    def test_missing_endtemplate(self, tmp_path):
        hoc = tmp_path / "cell.hoc"
        hoc.write_text(HOC_NO_END)
        with pytest.raises(ValueError, match="endtemplate"):
            check_structure(hoc)

    def test_mismatched_endtemplate(self, tmp_path):
        hoc = tmp_path / "cell.hoc"
        hoc.write_text(HOC_MISMATCHED_END)
        with pytest.raises(ValueError, match="endtemplate cADpyr_L2TPC"):
            check_structure(hoc)

    def test_accepts_string_path(self, tmp_path):
        hoc = tmp_path / "cell.hoc"
        hoc.write_text(VALID_HOC)
        check_structure(str(hoc))  # should not raise


class TestCheckMechanisms:
    def test_all_mechanisms_in_expected(self, tmp_path):
        hoc = tmp_path / "cell.hoc"
        hoc.write_text(HOC_WITH_CUSTOM_MECHANISM)
        check_mechanisms(hoc, {"NaTg", "Kv3_1"})  # pas is builtin, should pass

    def test_builtin_mechanisms_always_allowed(self, tmp_path):
        hoc = tmp_path / "cell.hoc"
        hoc.write_text(VALID_HOC)  # only uses pas and hh
        check_mechanisms(hoc, set())  # empty expected — builtins still pass

    def test_missing_mechanism_raises(self, tmp_path):
        hoc = tmp_path / "cell.hoc"
        hoc.write_text(HOC_WITH_CUSTOM_MECHANISM)
        with pytest.raises(ValueError, match="NaTg"):
            check_mechanisms(hoc, {"Kv3_1"})  # NaTg not in expected, not builtin

    def test_empty_hoc_no_inserts(self, tmp_path):
        hoc = tmp_path / "cell.hoc"
        hoc.write_text("begintemplate X\nendtemplate X\n")
        check_mechanisms(hoc, set())  # no mechanisms → no error

    def test_all_four_builtins_accepted(self, tmp_path):
        content = "begintemplate X\n"
        for mech in BUILTIN_NEURON_MECHANISMS:
            content += f"    insert {mech}\n"
        content += "endtemplate X\n"
        hoc = tmp_path / "cell.hoc"
        hoc.write_text(content)
        check_mechanisms(hoc, set())  # all builtins pass with empty expected


class TestBluecelulabInitializable:
    def test_calls_cell_with_correct_args(self, tmp_path):
        hoc = tmp_path / "cell.hoc"
        morph = tmp_path / "morph.swc"
        hoc.write_text("fake")
        morph.write_text("fake")

        mock_cell = MagicMock()
        mock_emodel_props = MagicMock()

        with (
            patch("bluecellulab.Cell", mock_cell),
            patch(
                "bluecellulab.circuit.circuit_access.definition.EmodelProperties",
                return_value=mock_emodel_props,
            ) as mock_props_cls,
        ):
            bluecellulab_initializable(
                hoc_path=str(hoc),
                morphology_path=str(morph),
                template_format="v6",
                holding_current=0.1,
                threshold_current=0.2,
            )

        mock_props_cls.assert_called_once_with(holding_current=0.1, threshold_current=0.2)
        mock_cell.assert_called_once_with(
            template_path=str(hoc),
            morphology_path=str(morph),
            template_format="v6",
            emodel_properties=mock_emodel_props,
        )

    def test_propagates_cell_error(self, tmp_path):
        hoc = tmp_path / "cell.hoc"
        morph = tmp_path / "morph.swc"
        hoc.write_text("fake")
        morph.write_text("fake")

        with (
            patch(
                "bluecellulab.Cell",
                side_effect=RuntimeError("NEURON error"),
            ),
            patch("bluecellulab.circuit.circuit_access.definition.EmodelProperties"),
            pytest.raises(RuntimeError, match="NEURON error"),
        ):
            bluecellulab_initializable(hoc_path=str(hoc), morphology_path=str(morph))

"""Tests for emodel_parameters module."""

from unittest.mock import MagicMock

import pytest

from obi_one.scientific.library.emodel_parameters import (
    _VALID_SECTION_LISTS,
    _expand_section_list,
    _parse_optimization_parameters,
)


def _make_emodel(ion_channel_models=None):
    """Create a mock EModel with optional ion channel models."""
    emodel = MagicMock()
    emodel.ion_channel_models = ion_channel_models or []
    return emodel


def _make_icm(suffix, name=None, range_vars=None, global_vars=None):
    """Create a mock IonChannelModel."""
    icm = MagicMock()
    icm.nmodl_suffix = suffix
    icm.name = name or suffix

    neuron_block = MagicMock()
    neuron_block.range = range_vars or []
    neuron_block.global_ = global_vars or []
    icm.neuron_block = neuron_block

    return icm


class TestValidSectionLists:
    """Tests for _VALID_SECTION_LISTS constant."""

    def test_contains_standard_sections(self):
        """Standard section lists are included."""
        assert "somatic" in _VALID_SECTION_LISTS
        assert "basal" in _VALID_SECTION_LISTS
        assert "apical" in _VALID_SECTION_LISTS
        assert "axonal" in _VALID_SECTION_LISTS

    def test_contains_multiloc_aliases(self):
        """Multi-location aliases are included."""
        assert "all" in _VALID_SECTION_LISTS
        assert "alldend" in _VALID_SECTION_LISTS
        assert "somadend" in _VALID_SECTION_LISTS
        assert "allnoaxon" in _VALID_SECTION_LISTS
        assert "somaxon" in _VALID_SECTION_LISTS
        assert "allact" in _VALID_SECTION_LISTS


class TestExpandSectionList:
    """Tests for _expand_section_list."""

    def test_expand_all(self):
        """'all' expands to all 4 section lists."""
        result = _expand_section_list("all")
        assert result == ["apical", "basal", "somatic", "axonal"]

    def test_expand_alldend(self):
        """'alldend' expands to apical and basal."""
        result = _expand_section_list("alldend")
        assert result == ["apical", "basal"]

    def test_passthrough_unknown(self):
        """Unknown section lists pass through unchanged."""
        result = _expand_section_list("somatic")
        assert result == ["somatic"]


class TestParseOptimizationParameters:
    """Tests for _parse_optimization_parameters."""

    def test_skips_distribution_meta_parameters(self):
        """Distribution meta-parameters (e.g. 'constant.distribution_decay') are skipped.

        These have a section_list that is not a recognized section list name
        AND the neuron_variable has no ion channel suffix.
        """
        icm = _make_icm("NaTg")
        emodel = _make_emodel(ion_channel_models=[icm])

        parameters_json = [
            # This is a distribution meta-parameter that should be skipped:
            # "constant" has no known suffix, "distribution_decay" is not a valid section list
            {"name": "constant.distribution_decay", "value": 0.5},
            # This is a valid parameter that should NOT be skipped:
            {"name": "gNaTgbar_NaTg.somatic", "value": 0.1},
        ]

        result = _parse_optimization_parameters(parameters_json, emodel)

        # Only the valid parameter should be in the result
        assert len(result) == 1
        assert result[0].neuron_variable == "gNaTgbar_NaTg"
        assert result[0].section_list == "somatic"
        assert result[0].value == pytest.approx(0.1)

    def test_skips_multiple_distribution_params(self):
        """Multiple distribution meta-parameters are all skipped."""
        icm = _make_icm("NaTg")
        emodel = _make_emodel(ion_channel_models=[icm])

        parameters_json = [
            {"name": "constant.distribution_decay", "value": 0.5},
            {"name": "exponential.scale_factor", "value": 1.2},
            {"name": "linear.offset_value", "value": 0.01},
            {"name": "gNaTgbar_NaTg.somatic", "value": 0.1},
        ]

        result = _parse_optimization_parameters(parameters_json, emodel)

        # Only the valid parameter should remain
        assert len(result) == 1
        assert result[0].neuron_variable == "gNaTgbar_NaTg"

    def test_does_not_skip_param_with_known_suffix_and_unknown_section(self):
        """Parameters with a recognized ion channel suffix are kept even if section_list is unusual.

        E.g. 'decay_CaDynamics_DC0.some_other' has suffix 'CaDynamics_DC0' which is known,
        so it should NOT be skipped even though 'some_other' is not a standard section list.
        """
        icm = _make_icm("CaDynamics_DC0")
        emodel = _make_emodel(ion_channel_models=[icm])

        parameters_json = [
            {"name": "decay_CaDynamics_DC0.some_custom_section", "value": 2.0},
        ]

        result = _parse_optimization_parameters(parameters_json, emodel)

        # Should NOT be skipped because the suffix is known
        assert len(result) == 1
        assert result[0].neuron_variable == "decay_CaDynamics_DC0"

    def test_valid_section_list_params_are_kept(self):
        """Parameters with valid section lists are parsed normally."""
        icm = _make_icm("pas")
        emodel = _make_emodel(ion_channel_models=[icm])

        parameters_json = [
            {"name": "g_pas.all", "value": 0.001},
            {"name": "e_pas.somatic", "value": -75.0},
        ]

        result = _parse_optimization_parameters(parameters_json, emodel)

        # "all" expands to 4 section lists
        g_pas_vars = [v for v in result if v.neuron_variable == "g_pas"]
        e_pas_vars = [v for v in result if v.neuron_variable == "e_pas"]

        assert len(g_pas_vars) == 4  # "all" expands to apical, basal, somatic, axonal
        assert len(e_pas_vars) == 1
        assert e_pas_vars[0].section_list == "somatic"

    def test_multiloc_alias_expansion(self):
        """Multi-location aliases are properly expanded."""
        icm = _make_icm("pas")
        emodel = _make_emodel(ion_channel_models=[icm])

        parameters_json = [
            {"name": "g_pas.alldend", "value": 0.001},
        ]

        result = _parse_optimization_parameters(parameters_json, emodel)

        # "alldend" expands to apical and basal
        assert len(result) == 2
        section_lists = {v.section_list for v in result}
        assert section_lists == {"apical", "basal"}

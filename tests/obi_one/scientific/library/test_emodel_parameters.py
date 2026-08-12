"""Tests for emodel_parameters module."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from entitysdk.types import AssetLabel

from obi_one.scientific.library.emodel_parameters import (
    _VALID_SECTION_LISTS,
    ChannelInfo,
    ChannelSectionListMapping,
    MechanismVariable,
    _build_channel_entity_id_mapping,
    _build_suffix_to_channel_name_mapping,
    _expand_section_list,
    _expand_section_lists,
    _extract_channel_suffix,
    _extract_section_properties,
    _fetch_optimization_parameters,
    _get_ion_channel_variables,
    _infer_section_lists_for_ion_channel_vars,
    _parse_optimization_parameters,
    get_mechanism_variables,
    get_mechanism_variables_for_emodel,
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

    def test_expand_section_lists_deduplicates_in_input_order(self):
        result = _expand_section_lists(["alldend", "somatic", "apical"])

        assert result == ["apical", "basal", "somatic"]


class TestMetadataHelpers:
    """Tests for channel metadata helper branches."""

    def test_channel_suffix_handles_missing_and_builtin_suffixes(self):
        assert _extract_channel_suffix("cm", ["NaTg"]) is None
        assert _extract_channel_suffix("g_pas", ["NaTg"]) == "pas"
        assert _extract_channel_suffix("gNaTgbar_NaTg", ["NaTg"]) == "NaTg"

    def test_channel_mappings_skip_incomplete_entries(self):
        first = SimpleNamespace(id="channel-id", name="NaTg", nmodl_suffix="NaTg")
        no_name = SimpleNamespace(id=None, name="", nmodl_suffix="pas")
        no_suffix = SimpleNamespace(id="other-id", name="Other", nmodl_suffix="")
        emodel = SimpleNamespace(ion_channel_models=[first, no_name, no_suffix])

        assert _build_suffix_to_channel_name_mapping(emodel) == {"NaTg": "NaTg"}
        assert _build_channel_entity_id_mapping(emodel) == {
            "NaTg": "channel-id",
            "Other": "other-id",
        }

    def test_inference_skips_optimized_and_unknown_variables(self):
        variable = MechanismVariable(
            neuron_variable="gNaTgbar_NaTg",
            section_list="somatic",
            variable_type="RANGE",
        )
        unknown = MechanismVariable(
            neuron_variable="gUnknown",
            section_list="all",
            variable_type="RANGE",
        )
        mapping = ChannelSectionListMapping(
            channel_to_section_lists={
                "NaTg": ChannelInfo(section_lists=["somatic"], entity_id=None)
            }
        )

        result = _infer_section_lists_for_ion_channel_vars(
            [variable, unknown],
            optimized_keys={("gNaTgbar_NaTg", "somatic")},
            channel_mapping=mapping,
            suffix_to_channel_name={"NaTg": "NaTg"},
            known_suffixes=["NaTg"],
        )

        assert result == []


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


class TestMechanismVariableLoading:
    """Tests for loading mechanism variables from EModel metadata and output."""

    def test_get_mechanism_variables_delegates_by_emodel_id(self):
        db_client = MagicMock()
        memodel = SimpleNamespace(emodel=SimpleNamespace(id="emodel-id"))
        expected = ([], ChannelSectionListMapping(channel_to_section_lists={}))

        with patch(
            "obi_one.scientific.library.emodel_parameters.get_mechanism_variables_for_emodel",
            return_value=expected,
        ) as mock_get:
            result = get_mechanism_variables(db_client, memodel)

        assert result == expected
        mock_get.assert_called_once_with(db_client, "emodel-id")

    def test_emodel_without_assets_adds_default_section_properties(self):
        db_client = MagicMock()
        emodel = SimpleNamespace(id="emodel-id", ion_channel_models=[], assets=[])
        db_client.get_entity.return_value = emodel

        variables, mapping = get_mechanism_variables_for_emodel(db_client, "emodel-id")

        db_client.get_entity.assert_called_once()
        assert db_client.get_entity.call_args.kwargs["entity_id"] == "emodel-id"
        assert db_client.get_entity.call_args.kwargs["entity_type"].__name__ == "EModel"
        assert mapping.channel_to_section_lists == {}
        assert len(variables) == 8
        assert {variable.neuron_variable for variable in variables} == {"cm", "Ra"}
        assert {variable.section_list for variable in variables} == {
            "somatic",
            "apical",
            "basal",
            "axonal",
        }

    def test_ion_channel_variables_filter_currents_and_include_range_and_global(self):
        ion_channel = SimpleNamespace(
            nmodl_suffix="NaTg",
            neuron_block=SimpleNamespace(
                range=[{"gNaTgbar": "mS/cm2", "iNaTg": "mA"}],
                global_=[{"vshift": "mV"}],
            ),
        )
        emodel = SimpleNamespace(ion_channel_models=[ion_channel])

        variables = _get_ion_channel_variables(emodel)

        assert {variable.neuron_variable for variable in variables} == {
            "gNaTgbar_NaTg",
            "vshift_NaTg",
        }
        assert all(variable.section_list == "all" for variable in variables)
        assert (
            next(v for v in variables if v.neuron_variable == "vshift_NaTg").variable_type
            == "GLOBAL"
        )
        assert next(v for v in variables if v.neuron_variable == "gNaTgbar_NaTg").limits == [
            0.0,
            10.0,
        ]

    def test_ion_channel_without_neuron_block_is_skipped(self):
        emodel = SimpleNamespace(
            ion_channel_models=[
                SimpleNamespace(nmodl_suffix="NaTg", neuron_block=None),
                SimpleNamespace(
                    nmodl_suffix="pas",
                    neuron_block=SimpleNamespace(range=[], global_=[]),
                ),
            ]
        )

        assert _get_ion_channel_variables(emodel) == []

    def test_global_optimization_parameter_is_detected(self):
        icm = _make_icm("NaTg", global_vars=[{"vshift": "mV"}])
        emodel = _make_emodel(ion_channel_models=[icm])

        result = _parse_optimization_parameters(
            [{"name": "vshift_NaTg.somatic", "value": 1.0}], emodel
        )

        assert result[0].variable_type == "GLOBAL"

    def test_parameter_without_section_list_uses_all(self):
        emodel = _make_emodel(ion_channel_models=[_make_icm("pas")])

        result = _parse_optimization_parameters([{"name": "g_pas", "value": 0.001}], emodel)

        assert len(result) == 4
        assert {variable.section_list for variable in result} == {
            "apical",
            "basal",
            "somatic",
            "axonal",
        }

    def test_optimization_output_asset_is_downloaded_and_parsed(self):
        asset = SimpleNamespace(label=AssetLabel.emodel_optimization_output, id="asset-id")
        emodel = SimpleNamespace(
            id="emodel-id",
            assets=[asset],
            ion_channel_models=[_make_icm("NaTg")],
        )
        db_client = MagicMock()
        db_client.download_content.return_value = (
            b'{"parameter": [{"name": "gNaTgbar_NaTg.somatic", "value": 0.2}]}'
        )

        result = _fetch_optimization_parameters(db_client, emodel)

        db_client.download_content.assert_called_once()
        assert result[0].neuron_variable == "gNaTgbar_NaTg"
        assert result[0].value == pytest.approx(0.2)

    def test_section_properties_follow_channel_mapping(self):
        mapping = ChannelSectionListMapping(
            channel_to_section_lists={
                "NaTg": ChannelInfo(section_lists=["somatic", "axonal"], entity_id="channel-id")
            }
        )

        variables = _extract_section_properties(mapping)

        assert len(variables) == 4
        assert {variable.section_list for variable in variables} == {"somatic", "axonal"}
        assert {variable.neuron_variable for variable in variables} == {"cm", "Ra"}
        assert all(variable.value is None for variable in variables)

    def test_emodel_output_and_metadata_are_merged(self):
        db_client = MagicMock()
        ion_channel = SimpleNamespace(
            id="channel-id",
            name="NaTg",
            nmodl_suffix="NaTg",
            neuron_block=SimpleNamespace(range=[], global_=[]),
        )
        emodel = SimpleNamespace(ion_channel_models=[ion_channel], assets=[])
        db_client.get_entity.return_value = emodel
        optimized = [
            MechanismVariable(
                neuron_variable="gNaTgbar_NaTg",
                section_list="somatic",
                value=0.1,
                limits=[0.0, 10.0],
                variable_type="RANGE",
            ),
            MechanismVariable(
                neuron_variable="vshift_NaTg",
                section_list="",
                variable_type="GLOBAL",
            ),
        ]
        metadata_variables = [
            MechanismVariable(
                neuron_variable="gNaTg_NaTg",
                section_list="all",
                limits=[0.0, 10.0],
                variable_type="RANGE",
            ),
            MechanismVariable(
                neuron_variable="vmin_NaTg",
                section_list="all",
                variable_type="GLOBAL",
            ),
        ]

        with (
            patch(
                "obi_one.scientific.library.emodel_parameters._fetch_optimization_parameters",
                return_value=optimized,
            ),
            patch(
                "obi_one.scientific.library.emodel_parameters._get_ion_channel_variables",
                return_value=metadata_variables,
            ),
        ):
            variables, mapping = get_mechanism_variables_for_emodel(db_client, "emodel-id")

        assert mapping.channel_to_section_lists["NaTg"].section_lists == ["somatic"]
        variable_names = {variable.neuron_variable for variable in variables}
        assert {
            "gNaTgbar_NaTg",
            "gNaTg_NaTg",
            "vshift_NaTg",
            "vmin_NaTg",
            "cm",
            "Ra",
        } <= variable_names
        assert (
            next(v for v in variables if v.neuron_variable == "gNaTg_NaTg").section_list
            == "somatic"
        )
        assert not next(v for v in variables if v.neuron_variable == "vmin_NaTg").section_list

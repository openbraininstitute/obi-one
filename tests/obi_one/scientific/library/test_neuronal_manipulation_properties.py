"""Tests for _compute_common_mechanism_variables and related pure-logic functions."""

from unittest.mock import MagicMock

import pytest

from obi_one.scientific.library.memodel_circuit import (
    IonChannelVariables,
    MechanismVariableDetail,
)
from obi_one.scientific.library.neuronal_manipulation_properties import (
    _compute_common_mechanism_variables,
    _match_templates_to_emodels,
    _resolve_population_and_node_ids,
)


def _make_emodel_group(
    node_ids: list[int],
    template: str,
    channels: dict[str, IonChannelVariables],
) -> dict:
    """Helper to build an emodel group dict matching the internal structure."""
    return {
        "node_ids": node_ids,
        "model_template": template,
        "mechanism_variables_by_ion_channel": channels,
    }


def _make_channel(
    section_lists: list[str],
    variables: dict[str, MechanismVariableDetail],
    entity_id: str | None = "some-entity-id",
) -> IonChannelVariables:
    return IonChannelVariables(
        section_lists=section_lists,
        entity_id=entity_id,
        variables=variables,
    )


def _make_var(
    units: str = "S/cm2",
    limits: list[float] | None = None,
    variable_type: str = "RANGE",
    section_lists_original_values: dict[str, float | None] | None = None,
) -> MechanismVariableDetail:
    return MechanismVariableDetail(
        units=units,
        limits=limits if limits is not None else [0.0, 1.0],
        variable_type=variable_type,
        section_lists_original_values=section_lists_original_values or {"somatic": 0.05},
    )


class TestComputeCommonMechanismVariables:
    """Tests for _compute_common_mechanism_variables."""

    def test_empty_input(self):
        """Empty dict returns empty dict."""
        result = _compute_common_mechanism_variables({})
        assert result == {}

    def test_single_emodel_group(self):
        """Single group returns its variables directly (no intersection needed)."""
        channel = _make_channel(
            section_lists=["somatic", "axonal"],
            variables={"gNaTgbar_NaTg": _make_var(limits=[0.0, 1.0])},
            entity_id="emodel-1-entity",
        )
        groups = {
            "emodel-1": _make_emodel_group([0, 1, 2], "hoc:cADpyr_L5TPC", {"NaTg": channel}),
        }

        result = _compute_common_mechanism_variables(groups)

        # Single group: returns its full set with original values preserved
        assert "NaTg" in result
        assert result["NaTg"].entity_id == "emodel-1-entity"
        assert result["NaTg"].section_lists == ["somatic", "axonal"]
        assert "gNaTgbar_NaTg" in result["NaTg"].variables

    def test_two_emodels_full_overlap(self):
        """Both groups have identical channels/variables → intersection = full set."""
        var1 = _make_var(limits=[0.0, 1.0], section_lists_original_values={"somatic": 0.04})
        var2 = _make_var(limits=[0.0, 0.8], section_lists_original_values={"somatic": 0.06})

        groups = {
            "emodel-1": _make_emodel_group(
                [0, 1],
                "hoc:cADpyr_L5TPC",
                {"NaTg": _make_channel(["somatic"], {"gNaTgbar_NaTg": var1})},
            ),
            "emodel-2": _make_emodel_group(
                [2, 3],
                "hoc:bAC_L6BTC",
                {"NaTg": _make_channel(["somatic"], {"gNaTgbar_NaTg": var2})},
            ),
        }

        result = _compute_common_mechanism_variables(groups)

        assert "NaTg" in result
        assert result["NaTg"].section_lists == ["somatic"]
        assert result["NaTg"].entity_id is None  # ambiguous across emodels
        var = result["NaTg"].variables["gNaTgbar_NaTg"]
        # Most restrictive limits: max(0.0, 0.0)=0.0, min(1.0, 0.8)=0.8
        assert var.limits == [0.0, 0.8]
        # Original values are None (ambiguous)
        assert var.section_lists_original_values == {"somatic": None}

    def test_two_emodels_partial_overlap(self):
        """Channel A in both, channel B only in one → intersection has only A."""
        var_a = _make_var(limits=[0.0, 1.0])

        groups = {
            "emodel-1": _make_emodel_group(
                [0],
                "hoc:cADpyr_L5TPC",
                {
                    "NaTg": _make_channel(["somatic"], {"gNaTgbar_NaTg": var_a}),
                    "SK_E2": _make_channel(["somatic"], {"gSK_E2bar": _make_var()}),
                },
            ),
            "emodel-2": _make_emodel_group(
                [1],
                "hoc:bAC_L6BTC",
                {
                    "NaTg": _make_channel(["somatic"], {"gNaTgbar_NaTg": var_a}),
                },
            ),
        }

        result = _compute_common_mechanism_variables(groups)

        assert "NaTg" in result
        assert "SK_E2" not in result

    def test_two_emodels_no_overlap(self):
        """Completely different channels → empty intersection."""
        groups = {
            "emodel-1": _make_emodel_group(
                [0],
                "hoc:cADpyr_L5TPC",
                {"NaTg": _make_channel(["somatic"], {"gNaTgbar_NaTg": _make_var()})},
            ),
            "emodel-2": _make_emodel_group(
                [1],
                "hoc:bAC_L6BTC",
                {"SK_E2": _make_channel(["somatic"], {"gSK_E2bar": _make_var()})},
            ),
        }

        result = _compute_common_mechanism_variables(groups)
        assert result == {}

    def test_variable_level_intersection(self):
        """Same channel but different variables → only common variables kept."""
        groups = {
            "emodel-1": _make_emodel_group(
                [0],
                "hoc:cADpyr_L5TPC",
                {
                    "NaTg": _make_channel(
                        ["somatic"],
                        {
                            "gNaTgbar_NaTg": _make_var(),
                            "vshiftm_NaTg": _make_var(),
                        },
                    ),
                },
            ),
            "emodel-2": _make_emodel_group(
                [1],
                "hoc:bAC_L6BTC",
                {
                    "NaTg": _make_channel(
                        ["somatic"],
                        {
                            "gNaTgbar_NaTg": _make_var(),
                            "vshifth_NaTg": _make_var(),  # different variable
                        },
                    ),
                },
            ),
        }

        result = _compute_common_mechanism_variables(groups)

        assert "NaTg" in result
        assert "gNaTgbar_NaTg" in result["NaTg"].variables
        assert "vshiftm_NaTg" not in result["NaTg"].variables
        assert "vshifth_NaTg" not in result["NaTg"].variables

    def test_section_list_intersection(self):
        """Same channel+variable but different section_lists → only common kept."""
        groups = {
            "emodel-1": _make_emodel_group(
                [0],
                "hoc:cADpyr_L5TPC",
                {
                    "NaTg": _make_channel(
                        ["somatic", "axonal", "apical"],
                        {"gNaTgbar_NaTg": _make_var()},
                    ),
                },
            ),
            "emodel-2": _make_emodel_group(
                [1],
                "hoc:bAC_L6BTC",
                {
                    "NaTg": _make_channel(
                        ["somatic", "axonal"],
                        {"gNaTgbar_NaTg": _make_var()},
                    ),
                },
            ),
        }

        result = _compute_common_mechanism_variables(groups)

        assert result["NaTg"].section_lists == ["axonal", "somatic"]  # sorted intersection

    def test_section_list_empty_intersection_excludes_channel(self):
        """If section_list intersection is empty, channel is excluded."""
        groups = {
            "emodel-1": _make_emodel_group(
                [0],
                "hoc:cADpyr_L5TPC",
                {"NaTg": _make_channel(["somatic"], {"gNaTgbar_NaTg": _make_var()})},
            ),
            "emodel-2": _make_emodel_group(
                [1],
                "hoc:bAC_L6BTC",
                {"NaTg": _make_channel(["axonal"], {"gNaTgbar_NaTg": _make_var()})},
            ),
        }

        result = _compute_common_mechanism_variables(groups)
        assert result == {}

    def test_limit_merging(self):
        """Limits are merged to most restrictive range."""
        groups = {
            "emodel-1": _make_emodel_group(
                [0],
                "hoc:cADpyr_L5TPC",
                {
                    "NaTg": _make_channel(
                        ["somatic"],
                        {"gNaTgbar_NaTg": _make_var(limits=[0.0, 1.0])},
                    ),
                },
            ),
            "emodel-2": _make_emodel_group(
                [1],
                "hoc:bAC_L6BTC",
                {
                    "NaTg": _make_channel(
                        ["somatic"],
                        {"gNaTgbar_NaTg": _make_var(limits=[0.1, 0.5])},
                    ),
                },
            ),
        }

        result = _compute_common_mechanism_variables(groups)
        assert result["NaTg"].variables["gNaTgbar_NaTg"].limits == [0.1, 0.5]

    def test_none_limits(self):
        """If all groups have None limits, result has None limits."""
        var_no_limits = MechanismVariableDetail(
            units="S/cm2",
            limits=None,
            variable_type="RANGE",
            section_lists_original_values={"somatic": 0.05},
        )
        groups = {
            "emodel-1": _make_emodel_group(
                [0],
                "hoc:cADpyr_L5TPC",
                {"NaTg": _make_channel(["somatic"], {"gNaTgbar_NaTg": var_no_limits})},
            ),
            "emodel-2": _make_emodel_group(
                [1],
                "hoc:bAC_L6BTC",
                {"NaTg": _make_channel(["somatic"], {"gNaTgbar_NaTg": var_no_limits})},
            ),
        }

        result = _compute_common_mechanism_variables(groups)
        assert result["NaTg"].variables["gNaTgbar_NaTg"].limits is None

    def test_group_with_failed_fetch_excluded(self):
        """Groups with empty mechanism_variables (fetch failed) are excluded."""
        groups = {
            "emodel-1": _make_emodel_group(
                [0],
                "hoc:cADpyr_L5TPC",
                {"NaTg": _make_channel(["somatic"], {"gNaTgbar_NaTg": _make_var()})},
            ),
            "emodel-2": _make_emodel_group(
                [1],
                "hoc:bAC_L6BTC",
                {},  # fetch failed
            ),
        }

        result = _compute_common_mechanism_variables(groups)

        # Only emodel-1 has vars, so it's treated as single group
        assert "NaTg" in result


class TestMatchTemplatesToEmodels:
    """Tests for _match_templates_to_emodels."""

    def test_all_matched(self):
        """Every template has a derivation."""
        node_to_template = {0: "hoc:cADpyr_L5TPC", 1: "hoc:bAC_L6BTC"}
        label_to_emodel = {"hoc:cADpyr_L5TPC": "emodel-1", "hoc:bAC_L6BTC": "emodel-2"}

        matched, unmatched = _match_templates_to_emodels(node_to_template, label_to_emodel)

        assert matched == {0: "emodel-1", 1: "emodel-2"}
        assert unmatched == set()

    def test_some_unmatched(self):
        """One template has no derivation."""
        node_to_template = {0: "hoc:cADpyr_L5TPC", 1: "hoc:unknown"}
        label_to_emodel = {"hoc:cADpyr_L5TPC": "emodel-1"}

        matched, unmatched = _match_templates_to_emodels(node_to_template, label_to_emodel)

        assert matched == {0: "emodel-1"}
        assert unmatched == {"hoc:unknown"}

    def test_all_unmatched(self):
        """No derivations exist."""
        node_to_template = {0: "hoc:cADpyr_L5TPC", 1: "hoc:bAC_L6BTC"}
        label_to_emodel: dict[str, str] = {}

        matched, unmatched = _match_templates_to_emodels(node_to_template, label_to_emodel)

        assert matched == {}
        assert unmatched == {"hoc:cADpyr_L5TPC", "hoc:bAC_L6BTC"}

    def test_empty_nodes(self):
        """No nodes to match."""
        matched, unmatched = _match_templates_to_emodels({}, {"hoc:x": "emodel-1"})
        assert matched == {}
        assert unmatched == set()


class TestResolvePopulationAndNodeIds:
    """Tests for _resolve_population_and_node_ids edge cases."""

    def test_raises_when_neither_provided(self):
        """Raises ValueError when neither neuron_set nor node_ids provided."""
        with pytest.raises(ValueError, match="Either neuron_set or node_ids must be provided"):
            _resolve_population_and_node_ids(
                db_client=MagicMock(),
                circuit_id="some-id",
                circuit_entity=MagicMock(),
                asset_id=MagicMock(),
                neuron_set=None,
                node_ids=None,
                population=None,
            )

    def test_node_ids_with_population_returns_directly(self):
        """When node_ids and population are provided, returns them without loading circuit."""
        db_client = MagicMock()
        result = _resolve_population_and_node_ids(
            db_client=db_client,
            circuit_id="some-id",
            circuit_entity=MagicMock(),
            asset_id=MagicMock(),
            neuron_set=None,
            node_ids=[0, 1, 2],
            population="my_pop",
        )

        assert result == ("my_pop", [0, 1, 2])
        # No fetch_file call needed since population was provided
        db_client.fetch_file.assert_not_called()

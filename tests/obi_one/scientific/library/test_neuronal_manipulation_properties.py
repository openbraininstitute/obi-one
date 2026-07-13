"""Tests for _compute_common_mechanism_variables and related pure-logic functions."""

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from obi_one.scientific.library.emodel_parameters import (
    ChannelInfo,
    ChannelSectionListMapping,
    MechanismVariable,
)
from obi_one.scientific.library.memodel_circuit import (
    IonChannelVariables,
    MechanismVariableDetail,
)
from obi_one.scientific.library.neuronal_manipulation_properties import (
    _build_emodel_groups,
    _compute_common_mechanism_variables,
    _fetch_emodel_derivation_mapping,
    _get_circuit_asset,
    _match_templates_to_emodels,
    get_circuit_manipulation_properties,
    get_circuit_node_ids,
)

TINY_CIRCUIT_DIR = Path("examples/data/tiny_circuits/N_10__top_nodes_dim6")

NATG_CHANNEL_MAPPING = ChannelSectionListMapping(
    channel_to_section_lists={"NaTg": ChannelInfo(section_lists=["somatic"], entity_id=None)}
)
SK_E2_CHANNEL_MAPPING = ChannelSectionListMapping(
    channel_to_section_lists={"SK_E2": ChannelInfo(section_lists=["somatic"], entity_id=None)}
)


def _make_fetch_file_side_effect(circuit_dir: Path):
    """Return a side effect that copies files from circuit_dir to output_path."""

    def _fetch_file(*, output_path, asset_path, **_kwargs):
        src = circuit_dir / asset_path
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, output_path)

    return _fetch_file


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


# --- Integration tests using tiny circuit data ---


@pytest.fixture
def mock_db_client():
    """Mock db_client with tiny circuit data."""
    client = MagicMock()
    asset = MagicMock()
    asset.is_directory = True
    asset.label.value = "sonata_circuit"
    asset.id = uuid4()
    entity = MagicMock()
    entity.name = "test_circuit"
    entity.assets = [asset]
    client.get_entity.return_value = entity
    client.fetch_file.side_effect = _make_fetch_file_side_effect(TINY_CIRCUIT_DIR)
    return client


class TestGetCircuitAsset:
    """Tests for _get_circuit_asset."""

    def test_returns_entity_and_asset_id(self, mock_db_client):
        """Returns circuit entity and asset ID."""
        entity, asset_id = _get_circuit_asset(mock_db_client, str(uuid4()))
        assert entity.name == "test_circuit"
        assert asset_id is not None

    def test_raises_when_no_sonata_asset(self):
        """Raises ValueError when no sonata_circuit directory asset."""
        client = MagicMock()
        entity = MagicMock()
        entity.assets = []  # no assets
        client.get_entity.return_value = entity

        with pytest.raises(ValueError, match="must have exactly one sonata_circuit"):
            _get_circuit_asset(client, str(uuid4()))

    def test_raises_when_asset_id_is_none(self):
        """Raises ValueError when asset ID is None."""
        client = MagicMock()
        asset = MagicMock()
        asset.is_directory = True
        asset.label.value = "sonata_circuit"
        asset.id = None
        entity = MagicMock()
        entity.assets = [asset]
        client.get_entity.return_value = entity

        with pytest.raises(ValueError, match="has no ID"):
            _get_circuit_asset(client, str(uuid4()))


class TestFetchEmodelDerivationMapping:
    """Tests for _fetch_emodel_derivation_mapping."""

    def test_builds_label_to_emodel_map(self):
        """Builds mapping from derivation labels."""
        client = MagicMock()
        deriv1 = MagicMock()
        deriv1.label = "hoc:cADpyr_L5TPC"
        deriv1.used.id = uuid4()
        deriv2 = MagicMock()
        deriv2.label = "hoc:bAC_L6BTC"
        deriv2.used.id = uuid4()
        client.search_entity.return_value.all.return_value = [deriv1, deriv2]

        result = _fetch_emodel_derivation_mapping(client, str(uuid4()))

        assert result["hoc:cADpyr_L5TPC"] == str(deriv1.used.id)
        assert result["hoc:bAC_L6BTC"] == str(deriv2.used.id)

    def test_skips_derivations_without_label(self):
        """Derivations with no label are skipped."""
        client = MagicMock()
        deriv = MagicMock()
        deriv.label = None
        client.search_entity.return_value.all.return_value = [deriv]

        result = _fetch_emodel_derivation_mapping(client, str(uuid4()))
        assert result == {}

    def test_empty_derivations(self):
        """No derivations returns empty dict."""
        client = MagicMock()
        client.search_entity.return_value.all.return_value = []

        result = _fetch_emodel_derivation_mapping(client, str(uuid4()))
        assert result == {}


class TestBuildEmodelGroups:
    """Tests for _build_emodel_groups."""

    def test_groups_nodes_by_emodel(self):
        """Groups nodes correctly and fetches variables."""
        client = MagicMock()
        emodel_id = str(uuid4())
        node_id_to_emodel = {0: emodel_id, 1: emodel_id, 2: emodel_id}
        label_to_emodel_id = {"hoc:cADpyr_L5TPC": emodel_id}

        with patch(
            "obi_one.scientific.library.neuronal_manipulation_properties"
            ".get_mechanism_variables_for_emodel"
        ) as mock_get_vars:
            mock_get_vars.return_value = (
                [
                    MechanismVariable(
                        neuron_variable="gNaTgbar_NaTg",
                        section_list="somatic",
                        value=0.04,
                        units="S/cm2",
                        limits=[0.0, 1.0],
                        variable_type="RANGE",
                        channel_name="NaTg",
                    )
                ],
                NATG_CHANNEL_MAPPING,
            )

            result = _build_emodel_groups(client, node_id_to_emodel, label_to_emodel_id)

        assert emodel_id in result
        assert result[emodel_id]["node_ids"] == [0, 1, 2]
        assert result[emodel_id]["model_template"] == "hoc:cADpyr_L5TPC"
        assert "mechanism_variables_by_ion_channel" in result[emodel_id]

    def test_handles_fetch_failure(self):
        """Groups with failed variable fetch get empty mechanism_variables."""
        client = MagicMock()
        emodel_id = str(uuid4())
        node_id_to_emodel = {0: emodel_id}
        label_to_emodel_id = {"hoc:cADpyr_L5TPC": emodel_id}

        with patch(
            "obi_one.scientific.library.neuronal_manipulation_properties"
            ".get_mechanism_variables_for_emodel",
            side_effect=Exception("fetch failed"),
        ):
            result = _build_emodel_groups(client, node_id_to_emodel, label_to_emodel_id)

        assert result[emodel_id]["mechanism_variables_by_ion_channel"] == {}


class TestGetCircuitManipulationPropertiesIntegration:
    """Integration test for get_circuit_manipulation_properties with mocked I/O."""

    def test_full_flow_with_neuron_set(self, mock_db_client):
        """Full flow: neuron_set → resolve templates → derivations → intersection."""
        circuit_id = str(uuid4())
        emodel_id_1 = str(uuid4())
        emodel_id_2 = str(uuid4())

        # Mock derivation search
        deriv1 = MagicMock()
        deriv1.label = "hoc:cACint_L23MC"
        deriv1.used.id = emodel_id_1
        deriv2 = MagicMock()
        deriv2.label = "hoc:cADpyr_L6BPC"
        deriv2.used.id = emodel_id_2
        mock_db_client.search_entity.return_value.all.return_value = [deriv1, deriv2]

        # Mock _resolve_neuron_set_and_get_templates to avoid file I/O
        mock_populations = ["S1nonbarrel_neurons"]
        mock_templates = {0: "hoc:cACint_L23MC", 1: "hoc:cADpyr_L6BPC", 2: "hoc:cADpyr_L6BPC"}

        neuron_set = MagicMock()

        with (
            patch(
                "obi_one.scientific.library.neuronal_manipulation_properties"
                "._resolve_neuron_set_and_get_templates",
                return_value=(mock_populations, mock_templates),
            ),
            patch(
                "obi_one.scientific.library.neuronal_manipulation_properties"
                ".get_mechanism_variables_for_emodel"
            ) as mock_get_vars,
        ):
            # Both emodels share NaTg channel
            mock_get_vars.return_value = (
                [
                    MechanismVariable(
                        neuron_variable="gNaTgbar_NaTg",
                        section_list="somatic",
                        value=0.04,
                        units="S/cm2",
                        limits=[0.0, 1.0],
                        variable_type="RANGE",
                        channel_name="NaTg",
                    )
                ],
                NATG_CHANNEL_MAPPING,
            )

            result = get_circuit_manipulation_properties(
                db_client=mock_db_client,
                circuit_id=circuit_id,
                neuron_set=neuron_set,
            )

        assert result["entity_type"] == "circuit"
        assert result["populations"] == ["S1nonbarrel_neurons"]
        assert "MechanismVariablesByIonChannel" in result
        # Both emodels have NaTg, so intersection should contain it
        assert "NaTg" in result["MechanismVariablesByIonChannel"]
        assert result["warnings"] is None

    def test_unmatched_templates_produce_warnings(self, mock_db_client):
        """Unmatched model_template values appear in warnings."""
        circuit_id = str(uuid4())

        # No derivations at all
        mock_db_client.search_entity.return_value.all.return_value = []

        mock_templates = {0: "hoc:cACint_L23MC", 1: "hoc:cADpyr_L6BPC"}
        neuron_set = MagicMock()

        with patch(
            "obi_one.scientific.library.neuronal_manipulation_properties"
            "._resolve_neuron_set_and_get_templates",
            return_value=(["S1nonbarrel_neurons"], mock_templates),
        ):
            result = get_circuit_manipulation_properties(
                db_client=mock_db_client,
                circuit_id=circuit_id,
                neuron_set=neuron_set,
            )

        assert result["entity_type"] == "circuit"
        assert result["MechanismVariablesByIonChannel"] == {}
        assert result["warnings"] is not None
        assert any("No derivation found" in w for w in result["warnings"])

    def test_empty_intersection_produces_warning(self, mock_db_client):
        """When emodels have no common channels, a warning is produced."""
        circuit_id = str(uuid4())
        emodel_id_1 = str(uuid4())
        emodel_id_2 = str(uuid4())

        deriv1 = MagicMock()
        deriv1.label = "hoc:cACint_L23MC"
        deriv1.used.id = emodel_id_1
        deriv2 = MagicMock()
        deriv2.label = "hoc:cADpyr_L6BPC"
        deriv2.used.id = emodel_id_2
        mock_db_client.search_entity.return_value.all.return_value = [deriv1, deriv2]

        mock_templates = {0: "hoc:cACint_L23MC", 1: "hoc:cADpyr_L6BPC"}
        neuron_set = MagicMock()

        call_count = [0]

        def _mock_get_vars(_db_client, _emodel_id):
            call_count[0] += 1
            if call_count[0] == 1:
                return (
                    [
                        MechanismVariable(
                            neuron_variable="gNaTgbar_NaTg",
                            section_list="somatic",
                            value=0.04,
                            units="S/cm2",
                            limits=[0.0, 1.0],
                            variable_type="RANGE",
                            channel_name="NaTg",
                        )
                    ],
                    NATG_CHANNEL_MAPPING,
                )
            return (
                [
                    MechanismVariable(
                        neuron_variable="gSK_E2bar_SK_E2",
                        section_list="somatic",
                        value=0.01,
                        units="S/cm2",
                        limits=[0.0, 0.5],
                        variable_type="RANGE",
                        channel_name="SK_E2",
                    )
                ],
                SK_E2_CHANNEL_MAPPING,
            )

        with (
            patch(
                "obi_one.scientific.library.neuronal_manipulation_properties"
                "._resolve_neuron_set_and_get_templates",
                return_value=(["S1nonbarrel_neurons"], mock_templates),
            ),
            patch(
                "obi_one.scientific.library.neuronal_manipulation_properties"
                ".get_mechanism_variables_for_emodel",
                side_effect=_mock_get_vars,
            ),
        ):
            result = get_circuit_manipulation_properties(
                db_client=mock_db_client,
                circuit_id=circuit_id,
                neuron_set=neuron_set,
            )

        assert result["MechanismVariablesByIonChannel"] == {}
        assert result["warnings"] is not None
        assert any("No common mechanism variables" in w for w in result["warnings"])


class TestComputeCommonMechanismVariablesEdgeCases:
    """Additional edge case tests for _compute_common_mechanism_variables."""

    def test_all_groups_failed_fetch(self):
        """All groups have empty mechanism_variables → returns empty dict."""
        groups = {
            "emodel-1": _make_emodel_group([0], "hoc:cADpyr_L5TPC", {}),
            "emodel-2": _make_emodel_group([1], "hoc:bAC_L6BTC", {}),
        }

        result = _compute_common_mechanism_variables(groups)
        assert result == {}

    def test_common_channel_but_no_common_variables(self):
        """Same channel in both groups but completely different variables → channel excluded."""
        groups = {
            "emodel-1": _make_emodel_group(
                [0],
                "hoc:cADpyr_L5TPC",
                {"NaTg": _make_channel(["somatic"], {"gNaTgbar_NaTg": _make_var()})},
            ),
            "emodel-2": _make_emodel_group(
                [1],
                "hoc:bAC_L6BTC",
                {"NaTg": _make_channel(["somatic"], {"vshiftm_NaTg": _make_var()})},
            ),
        }

        result = _compute_common_mechanism_variables(groups)
        # NaTg is a common channel but has no common variables → excluded
        assert result == {}


class TestGetCircuitNodeIds:
    """Tests for get_circuit_node_ids with mocked neuron set."""

    def test_resolves_neuron_set_to_node_ids(self, mock_db_client):
        """Resolves a neuron set to node IDs using the circuit."""

        circuit_id = str(uuid4())

        # Mock neuron set that returns dict of node IDs per population
        neuron_set = MagicMock()
        neuron_set.get_neuron_ids.return_value = {"S1nonbarrel_neurons": [0, 1, 2, 3]}

        ids_per_population = get_circuit_node_ids(
            mock_db_client, circuit_id, neuron_set
        )

        assert ids_per_population == {"S1nonbarrel_neurons": [0, 1, 2, 3]}
        neuron_set.get_neuron_ids.assert_called_once()

    def test_resolves_multiple_populations(self, mock_db_client):
        """When neuron set spans multiple populations, returns all."""

        circuit_id = str(uuid4())

        neuron_set = MagicMock()
        neuron_set.get_neuron_ids.return_value = {
            "S1nonbarrel_neurons": [5, 6],
            "other_pop": [10, 11, 12],
        }

        ids_per_population = get_circuit_node_ids(
            mock_db_client, circuit_id, neuron_set
        )

        assert ids_per_population == {
            "S1nonbarrel_neurons": [5, 6],
            "other_pop": [10, 11, 12],
        }

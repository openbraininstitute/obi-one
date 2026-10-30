"""Tests for _compute_common_mechanism_variables and related pure-logic functions."""

import shutil
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch
from uuid import uuid4

import h5py
import httpx2
import pytest
from entitysdk.common import ProjectContext
from entitysdk.exception import EntitySDKError
from entitysdk.models import Derivation as DerivationModel, IonChannelModel
from entitysdk.models.asset import DetailedFile, DetailedFileList
from entitysdk.types import FetchFileStrategy
from libsonata import NodeStorage

from obi_one.core.exception import OBIONEError
from obi_one.scientific.blocks.neuron_sets.predefined import (
    BiophysicalPopulationPredefinedNeuronSet,
)
from obi_one.scientific.library import circuit as circuit_module
from obi_one.scientific.library.circuit import Circuit as ObiCircuit
from obi_one.scientific.library.emodel_circuit_files import HocTemplateError, ModMechanism
from obi_one.scientific.library.emodel_parameters import (
    ChannelInfo,
    ChannelSectionListMapping,
    MechanismVariable,
)
from obi_one.scientific.library.memodel_circuit import (
    IonChannelVariables,
    MechanismVariableDetail,
    MEModelCircuit,
    MEModelWithSynapsesCircuit,
    _build_mechanism_variables_by_ion_channel_response,
    get_memodel_mechanism_variables,
)
from obi_one.scientific.library.neuronal_manipulation_properties import (
    MAX_MODEL_FILE_BYTES,
    UNDECLARED_MOD_DIRS,
    PopulationModelDirs,
    TemplateModel,
    _asset_files,
    _build_emodel_groups,
    _compute_common_mechanism_variables,
    _database_units,
    _fetch_emodel_derivation_mapping,
    _fill_units_from_database,
    _get_circuit_asset,
    _match_templates_to_emodels,
    _population_templates,
    _public_reason,
    _read_model_file,
    _read_template_models,
    _relative_dir,
    _stage_circuit_for_neuron_set,
    _stage_circuit_for_neuron_set_resolution,
    _stage_file,
    _unique_templates,
    get_circuit_manipulation_properties,
    get_circuit_node_ids,
    get_expanded_neuron_ids,
)

from tests.obi_one.db_sdk.test_assets import storage_transport

TINY_CIRCUIT_DIR = Path("examples/data/tiny_circuits/N_10__top_nodes_dim6")

NATG_CHANNEL_MAPPING = ChannelSectionListMapping(
    channel_to_section_lists={"NaTg": ChannelInfo(section_lists=["somatic"], entity_id=None)}
)
SK_E2_CHANNEL_MAPPING = ChannelSectionListMapping(
    channel_to_section_lists={"SK_E2": ChannelInfo(section_lists=["somatic"], entity_id=None)}
)


EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _listing(circuit_dir: Path) -> DetailedFileList:
    """What entitysdk's ``list_directory`` returns for a circuit stored in ``circuit_dir``."""
    return DetailedFileList(
        files={
            path.relative_to(circuit_dir): DetailedFile(
                name=path.name, size=path.stat().st_size, last_modified=EPOCH
            )
            for path in circuit_dir.rglob("*")
            if path.is_file()
        }
    )


def _sonata_entity() -> MagicMock:
    """A circuit entity with one sonata_circuit directory asset."""
    asset = MagicMock()
    asset.is_directory = True
    asset.label.value = "sonata_circuit"
    asset.id = uuid4()
    entity = MagicMock()
    entity.name = "test_circuit"
    entity.assets = [asset]
    return entity


def _make_fetch_file_side_effect(circuit_dir: Path):
    """Return a side effect that copies files from circuit_dir to output_path."""

    def _fetch_file(*, output_path, asset_path, strategy=None, **_kwargs):
        if strategy == FetchFileStrategy.link_only:
            msg = "link strategy failed: Asset path not found in store"
            raise EntitySDKError(msg)  # no mounted asset store in tests
        src = circuit_dir / asset_path
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, output_path)

    return _fetch_file


def _serve_storage(client: MagicMock, circuit_dir: Path, *, redirect: bool = True) -> None:
    """Give a mock client the HTTP side the partial read uses (see ``storage_transport``)."""
    client.api_url = "http://entitycore/api/entitycore"
    client.project_context = ProjectContext(virtual_lab_id=uuid4(), project_id=uuid4())
    client._token_manager.get_token.return_value = "token"
    client._http_client = httpx2.Client(transport=storage_transport(circuit_dir, redirect=redirect))


def _make_link_or_copy_fetch_file_side_effect(circuit_dir: Path):
    """Return a side effect matching entitysdk's link-or-download behavior."""

    def _fetch_file(*, output_path, asset_path, strategy, **_kwargs):
        src = circuit_dir / asset_path
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if strategy == FetchFileStrategy.copy_or_download:
            shutil.copy2(src, output_path)
        else:
            output_path.symlink_to(src)

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
        """Both groups have identical channels/variables -> intersection = full set."""
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
        """Channel A in both, channel B only in one -> intersection has only A."""
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
        """Completely different channels -> empty intersection."""
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
        """Same channel but different variables -> only common variables kept."""
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
        """Same channel+variable but different section_lists -> only common kept."""
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
        node_to_template = {
            ("S1nonbarrel_neurons", 0): "hoc:cADpyr_L5TPC",
            ("S1nonbarrel_neurons", 1): "hoc:bAC_L6BTC",
        }
        label_to_emodel = {"hoc:cADpyr_L5TPC": "emodel-1", "hoc:bAC_L6BTC": "emodel-2"}

        matched, unmatched = _match_templates_to_emodels(node_to_template, label_to_emodel)

        assert matched == {
            ("S1nonbarrel_neurons", 0): "emodel-1",
            ("S1nonbarrel_neurons", 1): "emodel-2",
        }
        assert unmatched == set()

    def test_some_unmatched(self):
        """One template has no derivation."""
        node_to_template = {
            ("S1nonbarrel_neurons", 0): "hoc:cADpyr_L5TPC",
            ("S1nonbarrel_neurons", 1): "hoc:unknown",
        }
        label_to_emodel = {"hoc:cADpyr_L5TPC": "emodel-1"}

        matched, unmatched = _match_templates_to_emodels(node_to_template, label_to_emodel)

        assert matched == {("S1nonbarrel_neurons", 0): "emodel-1"}
        assert unmatched == {"hoc:unknown"}

    def test_all_unmatched(self):
        """No derivations exist."""
        node_to_template = {
            ("S1nonbarrel_neurons", 0): "hoc:cADpyr_L5TPC",
            ("S1nonbarrel_neurons", 1): "hoc:bAC_L6BTC",
        }
        label_to_emodel: dict[str, str] = {}

        matched, unmatched = _match_templates_to_emodels(node_to_template, label_to_emodel)

        assert matched == {}
        assert unmatched == {"hoc:cADpyr_L5TPC", "hoc:bAC_L6BTC"}

    def test_population_qualified_keys_prevent_collision(self):
        """Same node ID in different populations maps to different emodels."""
        node_to_template = {
            ("pop_A", 0): "hoc:cADpyr_L5TPC",
            ("pop_B", 0): "hoc:bAC_L6BTC",
        }
        label_to_emodel = {
            "hoc:cADpyr_L5TPC": "emodel-1",
            "hoc:bAC_L6BTC": "emodel-2",
        }

        matched, unmatched = _match_templates_to_emodels(node_to_template, label_to_emodel)

        assert matched == {
            ("pop_A", 0): "emodel-1",
            ("pop_B", 0): "emodel-2",
        }
        assert unmatched == set()

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
    client.get_entity.return_value = _sonata_entity()
    client.fetch_file.side_effect = _make_fetch_file_side_effect(TINY_CIRCUIT_DIR)
    client.list_directory.return_value = _listing(TINY_CIRCUIT_DIR)
    _serve_storage(client, TINY_CIRCUIT_DIR)
    return client


class TestGetCircuitAsset:
    """Tests for _get_circuit_asset."""

    def test_returns_entity_and_asset_id(self, mock_db_client):
        """Returns circuit entity and asset ID."""
        entity, asset = _get_circuit_asset(mock_db_client, str(uuid4()))
        assert entity.name == "test_circuit"
        assert asset.id is not None

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
        node_key_to_emodel = {
            ("S1nonbarrel_neurons", 0): emodel_id,
            ("S1nonbarrel_neurons", 1): emodel_id,
            ("S1nonbarrel_neurons", 2): emodel_id,
        }
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

            result = _build_emodel_groups(client, node_key_to_emodel, label_to_emodel_id)

        assert emodel_id in result
        assert result[emodel_id]["node_ids"] == [
            ("S1nonbarrel_neurons", 0),
            ("S1nonbarrel_neurons", 1),
            ("S1nonbarrel_neurons", 2),
        ]
        assert result[emodel_id]["model_template"] == "hoc:cADpyr_L5TPC"
        assert "mechanism_variables_by_ion_channel" in result[emodel_id]

    def test_handles_fetch_failure(self):
        """Groups with failed variable fetch get empty mechanism_variables."""
        client = MagicMock()
        emodel_id = str(uuid4())
        node_key_to_emodel = {("S1nonbarrel_neurons", 0): emodel_id}
        label_to_emodel_id = {"hoc:cADpyr_L5TPC": emodel_id}

        with patch(
            "obi_one.scientific.library.neuronal_manipulation_properties"
            ".get_mechanism_variables_for_emodel",
            side_effect=Exception("fetch failed"),
        ):
            result = _build_emodel_groups(client, node_key_to_emodel, label_to_emodel_id)

        assert result[emodel_id]["mechanism_variables_by_ion_channel"] == {}


class TestGetCircuitManipulationPropertiesIntegration:
    """Integration test for get_circuit_manipulation_properties with mocked I/O."""

    def test_full_flow_with_neuron_set(self, mock_db_client):
        """Full flow: neuron_set -> resolve templates -> derivations -> intersection."""
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

        # Mock _stage_circuit_for_neuron_set_resolution to avoid file I/O
        mock_populations = ["S1nonbarrel_neurons"]
        mock_templates = {
            ("S1nonbarrel_neurons", 0): "hoc:cACint_L23MC",
            ("S1nonbarrel_neurons", 1): "hoc:cADpyr_L6BPC",
            ("S1nonbarrel_neurons", 2): "hoc:cADpyr_L6BPC",
        }

        neuron_set = MagicMock()
        neuron_set.expand_multi_values.return_value = [neuron_set]

        with (
            patch(
                "obi_one.scientific.library.neuronal_manipulation_properties"
                "._stage_circuit_for_neuron_set_resolution",
                return_value=(mock_populations, mock_templates, {}),
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
        assert all("emodel_circuit derivation instead" in w for w in result["warnings"])

    def test_unmatched_templates_produce_warnings(self, mock_db_client):
        """Unmatched model_template values appear in warnings."""
        circuit_id = str(uuid4())

        # No derivations at all
        mock_db_client.search_entity.return_value.all.return_value = []

        mock_templates = {
            ("S1nonbarrel_neurons", 0): "hoc:cACint_L23MC",
            ("S1nonbarrel_neurons", 1): "hoc:cADpyr_L6BPC",
        }
        neuron_set = MagicMock()
        neuron_set.expand_multi_values.return_value = [neuron_set]

        with patch(
            "obi_one.scientific.library.neuronal_manipulation_properties"
            "._stage_circuit_for_neuron_set_resolution",
            return_value=(["S1nonbarrel_neurons"], mock_templates, {}),
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

        mock_templates = {
            ("S1nonbarrel_neurons", 0): "hoc:cACint_L23MC",
            ("S1nonbarrel_neurons", 1): "hoc:cADpyr_L6BPC",
        }
        neuron_set = MagicMock()
        neuron_set.expand_multi_values.return_value = [neuron_set]

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
                "._stage_circuit_for_neuron_set_resolution",
                return_value=(["S1nonbarrel_neurons"], mock_templates, {}),
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

    def test_multi_emodel_intersection_preserves_bounds(self, mock_db_client):
        """Multi-emodel intersection preserves hardcoded limits across emodels.

        Both emodels share the NaTg channel with the same conductance variable.
        Since limits are hardcoded (not per-emodel), the intersection should
        preserve them unchanged: [0.0, 20.0] for conductance variables.
        """
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

        mock_templates = {
            ("S1nonbarrel_neurons", 0): "hoc:cACint_L23MC",
            ("S1nonbarrel_neurons", 1): "hoc:cADpyr_L6BPC",
        }
        neuron_set = MagicMock()
        neuron_set.expand_multi_values.return_value = [neuron_set]

        def _mock_get_vars(_db_client, emodel_id):
            # Both emodels get the same hardcoded limits for conductance vars
            return (
                [
                    MechanismVariable(
                        neuron_variable="gNaTgbar_NaTg",
                        section_list="somatic",
                        value=0.04 if emodel_id == emodel_id_1 else 0.06,
                        units="S/cm2",
                        limits=[0.0, 10.0],
                        variable_type="RANGE",
                        channel_name="NaTg",
                    ),
                ],
                NATG_CHANNEL_MAPPING,
            )

        with (
            patch(
                "obi_one.scientific.library.neuronal_manipulation_properties"
                "._stage_circuit_for_neuron_set_resolution",
                return_value=(["S1nonbarrel_neurons"], mock_templates, {}),
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

        channels = result["MechanismVariablesByIonChannel"]
        assert "NaTg" in channels
        natg = channels["NaTg"]
        natg_var = natg.variables["gNaTgbar_NaTg"]
        # Both emodels have [0.0, 10.0] -> intersection preserves it
        assert natg_var.limits == [0.0, 10.0]
        assert natg_var.units == "S/cm2"
        assert natg_var.variable_type == "RANGE"
        assert natg.section_lists == ["somatic"]
        assert all("emodel_circuit derivation instead" in w for w in result["warnings"])


class TestComputeCommonMechanismVariablesEdgeCases:
    """Additional edge case tests for _compute_common_mechanism_variables."""

    def test_all_groups_failed_fetch(self):
        """All groups have empty mechanism_variables -> returns empty dict."""
        groups = {
            "emodel-1": _make_emodel_group([0], "hoc:cADpyr_L5TPC", {}),
            "emodel-2": _make_emodel_group([1], "hoc:bAC_L6BTC", {}),
        }

        result = _compute_common_mechanism_variables(groups)
        assert result == {}

    def test_common_channel_but_no_common_variables(self):
        """Same channel in both groups but completely different variables -> channel excluded."""
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
        # NaTg is a common channel but has no common variables -> excluded
        assert result == {}


class TestGetCircuitNodeIds:
    """Tests for get_circuit_node_ids with mocked neuron set."""

    def test_resolves_neuron_set_to_node_ids(self, mock_db_client):
        """Resolves a neuron set to node IDs using the circuit."""

        circuit_id = str(uuid4())

        # Mock neuron set that returns dict of node IDs per population
        neuron_set = MagicMock()
        neuron_set.expand_multi_values.return_value = [neuron_set]
        neuron_set.get_neuron_ids.return_value = {"S1nonbarrel_neurons": [0, 1, 2, 3]}

        ids_per_population = get_circuit_node_ids(mock_db_client, circuit_id, neuron_set)

        assert ids_per_population == {"S1nonbarrel_neurons": [0, 1, 2, 3]}
        neuron_set.get_neuron_ids.assert_called_once()

    def test_resolves_multiple_populations(self, mock_db_client):
        """When neuron set spans multiple populations, returns all."""

        circuit_id = str(uuid4())

        neuron_set = MagicMock()
        neuron_set.expand_multi_values.return_value = [neuron_set]
        neuron_set.get_neuron_ids.return_value = {
            "S1nonbarrel_neurons": [5, 6],
            "other_pop": [10, 11, 12],
        }

        ids_per_population = get_circuit_node_ids(mock_db_client, circuit_id, neuron_set)

        assert ids_per_population == {
            "S1nonbarrel_neurons": [5, 6],
            "other_pop": [10, 11, 12],
        }

    def test_resolves_swept_node_set_to_union(self, mock_db_client):
        """A list-valued node_set is expanded and its node IDs are unioned."""
        neuron_set = BiophysicalPopulationPredefinedNeuronSet(
            node_set=["L6_IPC", "L6_TPC:A"], population="S1nonbarrel_neurons"
        )

        result = get_circuit_node_ids(mock_db_client, str(uuid4()), neuron_set)

        obi_circuit = ObiCircuit(
            name="N_10__top_nodes_dim6",
            path=str(TINY_CIRCUIT_DIR / "circuit_config.json"),
        )
        expected = sorted(
            set(
                BiophysicalPopulationPredefinedNeuronSet(
                    node_set="L6_IPC", population="S1nonbarrel_neurons"
                ).get_neuron_ids(obi_circuit)["S1nonbarrel_neurons"]
            )
            | set(
                BiophysicalPopulationPredefinedNeuronSet(
                    node_set="L6_TPC:A", population="S1nonbarrel_neurons"
                ).get_neuron_ids(obi_circuit)["S1nonbarrel_neurons"]
            )
        )
        assert result == {"S1nonbarrel_neurons": expected}
        assert len(expected) > 0


class TestGetExpandedNeuronIds:
    """Tests for get_expanded_neuron_ids sweep expansion and per-population union."""

    @pytest.fixture
    def obi_circuit(self):
        return ObiCircuit(
            name="N_10__top_nodes_dim6",
            path=str(TINY_CIRCUIT_DIR / "circuit_config.json"),
        )

    def test_scalar_neuron_set_unchanged(self, obi_circuit):
        """A neuron set without swept fields resolves exactly as before."""
        neuron_set = BiophysicalPopulationPredefinedNeuronSet(
            node_set="Layer6", population="S1nonbarrel_neurons"
        )

        result = get_expanded_neuron_ids(neuron_set, obi_circuit)

        assert result == neuron_set.get_neuron_ids(obi_circuit)
        assert len(result["S1nonbarrel_neurons"]) == 9

    def test_node_set_list_unions_members(self, obi_circuit):
        """A swept node_set expands per name and unions the resolved IDs."""
        swept = BiophysicalPopulationPredefinedNeuronSet(
            node_set=["L6_IPC", "L6_TPC:A"], population="S1nonbarrel_neurons"
        )

        result = get_expanded_neuron_ids(swept, obi_circuit)

        ids_a = BiophysicalPopulationPredefinedNeuronSet(
            node_set="L6_IPC", population="S1nonbarrel_neurons"
        ).get_neuron_ids(obi_circuit)["S1nonbarrel_neurons"]
        ids_b = BiophysicalPopulationPredefinedNeuronSet(
            node_set="L6_TPC:A", population="S1nonbarrel_neurons"
        ).get_neuron_ids(obi_circuit)["S1nonbarrel_neurons"]
        assert result["S1nonbarrel_neurons"] == sorted(set(ids_a) | set(ids_b))

    def test_swept_sample_percentage_unions_subsets(self, obi_circuit):
        """A swept sample_percentage expands per value; 100% covers all sampled IDs."""
        swept = BiophysicalPopulationPredefinedNeuronSet(
            node_set="Layer6",
            population="S1nonbarrel_neurons",
            sample_percentage=[50, 100],
            sample_seed=1,
        )

        result = get_expanded_neuron_ids(swept, obi_circuit)

        full = BiophysicalPopulationPredefinedNeuronSet(
            node_set="Layer6", population="S1nonbarrel_neurons"
        ).get_neuron_ids(obi_circuit)["S1nonbarrel_neurons"]
        assert result["S1nonbarrel_neurons"] == sorted(full)

    def test_unknown_node_set_member_raises(self, obi_circuit):
        """An unknown name inside a swept node_set raises the usual error."""
        neuron_set = BiophysicalPopulationPredefinedNeuronSet(
            node_set=["L6_IPC", "NONEXISTENT"], population="S1nonbarrel_neurons"
        )

        with pytest.raises(ValueError, match="not found in circuit"):
            get_expanded_neuron_ids(neuron_set, obi_circuit)


class TestStageCircuitForNeuronSetResolution:
    """Tests for _stage_circuit_for_neuron_set_resolution using tiny circuit data."""

    def test_reads_model_templates_from_circuit(self, mock_db_client):
        """Stages circuit files and reads model_template for resolved node IDs."""
        circuit_id = str(uuid4())
        circuit_entity, asset = _get_circuit_asset(mock_db_client, circuit_id)

        neuron_set = MagicMock()
        neuron_set.expand_multi_values.return_value = [neuron_set]
        neuron_set.get_neuron_ids.return_value = {"S1nonbarrel_neurons": [0, 1, 2]}

        populations, node_to_template, _sources = _stage_circuit_for_neuron_set_resolution(
            db_client=mock_db_client,
            circuit_id=circuit_id,
            circuit_entity=circuit_entity,
            asset=asset,
            neuron_set=neuron_set,
        )

        assert populations == ["S1nonbarrel_neurons"]
        assert len(node_to_template) == 3
        # Keys are (population, node_id) tuples
        assert all(isinstance(k, tuple) and len(k) == 2 for k in node_to_template)
        assert all(k[0] == "S1nonbarrel_neurons" for k in node_to_template)
        # model_template values from tiny circuit
        assert all(t.startswith("hoc:") for t in node_to_template.values())

    def test_copies_config_before_loading_linked_circuit(self, tmp_path):
        """Config is copied (not symlinked) so $BASE_DIR resolves to temp dir."""
        circuit_dir = tmp_path / "circuit"
        shutil.copytree(TINY_CIRCUIT_DIR, circuit_dir)
        config_path = circuit_dir / "circuit_config.json"
        original_config = config_path.read_bytes()

        client = MagicMock()
        asset = MagicMock()
        asset.is_directory = True
        asset.label.value = "sonata_circuit"
        asset.id = uuid4()
        entity = MagicMock()
        entity.name = "test_circuit"
        entity.assets = [asset]
        client.get_entity.return_value = entity
        client.fetch_file.side_effect = _make_link_or_copy_fetch_file_side_effect(circuit_dir)

        neuron_set = MagicMock()
        neuron_set.expand_multi_values.return_value = [neuron_set]
        neuron_set.get_neuron_ids.return_value = {"S1nonbarrel_neurons": [0, 1, 2]}

        populations, node_to_template, _sources = _stage_circuit_for_neuron_set_resolution(
            db_client=client,
            circuit_id=str(uuid4()),
            circuit_entity=entity,
            asset=asset,
            neuron_set=neuron_set,
        )

        assert populations == ["S1nonbarrel_neurons"]
        assert len(node_to_template) == 3
        assert config_path.read_bytes() == original_config
        config_call = next(
            call
            for call in client.fetch_file.call_args_list
            if call.kwargs["asset_path"] == Path("circuit_config.json")
        )
        assert config_call.kwargs["strategy"] == FetchFileStrategy.copy_or_download

    def test_continues_without_node_sets_json(self, tmp_path):
        """Missing node_sets.json is logged and skipped, not raised."""
        circuit_dir = tmp_path / "circuit"
        shutil.copytree(TINY_CIRCUIT_DIR, circuit_dir)
        # Remove node_sets.json to trigger the exception path
        (circuit_dir / "node_sets.json").unlink()

        client = MagicMock()
        asset = MagicMock()
        asset.is_directory = True
        asset.label.value = "sonata_circuit"
        asset.id = uuid4()
        entity = MagicMock()
        entity.name = "test_circuit"
        entity.assets = [asset]
        client.get_entity.return_value = entity
        client.fetch_file.side_effect = _make_link_or_copy_fetch_file_side_effect(circuit_dir)

        neuron_set = MagicMock()
        neuron_set.expand_multi_values.return_value = [neuron_set]
        neuron_set.get_neuron_ids.return_value = {"S1nonbarrel_neurons": [0, 1, 2]}

        # Should not raise despite missing node_sets.json
        populations, node_to_template, _sources = _stage_circuit_for_neuron_set_resolution(
            db_client=client,
            circuit_id=str(uuid4()),
            circuit_entity=entity,
            asset=asset,
            neuron_set=neuron_set,
        )

        assert populations == ["S1nonbarrel_neurons"]
        assert len(node_to_template) == 3

    def test_raises_when_population_not_in_nodes_mapping(self, tmp_path):
        """Population returned by neuron set but missing from staging raises ValueError."""
        circuit_dir = tmp_path / "circuit"
        shutil.copytree(TINY_CIRCUIT_DIR, circuit_dir)

        client = MagicMock()
        asset = MagicMock()
        asset.is_directory = True
        asset.label.value = "sonata_circuit"
        asset.id = uuid4()
        entity = MagicMock()
        entity.name = "test_circuit"
        entity.assets = [asset]
        client.get_entity.return_value = entity
        client.fetch_file.side_effect = _make_link_or_copy_fetch_file_side_effect(circuit_dir)

        neuron_set = MagicMock()
        neuron_set.expand_multi_values.return_value = [neuron_set]
        # Return a population that doesn't exist in the circuit's nodes
        neuron_set.get_neuron_ids.return_value = {"nonexistent_pop": [0, 1]}

        with (
            patch(
                "obi_one.scientific.library.neuronal_manipulation_properties"
                "._stage_circuit_for_neuron_set",
                return_value=(
                    circuit_dir / "circuit_config.json",
                    {"S1nonbarrel_neurons": "nodes.h5"},
                    {},
                ),
            ),
            pytest.raises(ValueError, match="No nodes file found for population"),
        ):
            _stage_circuit_for_neuron_set_resolution(
                db_client=client,
                circuit_id=str(uuid4()),
                circuit_entity=entity,
                asset=asset,
                neuron_set=neuron_set,
            )

    def test_raises_when_neuron_set_resolves_to_no_nodes(self, mock_db_client):
        """Empty node IDs raises ValueError."""
        circuit_id = str(uuid4())
        circuit_entity, asset = _get_circuit_asset(mock_db_client, circuit_id)

        neuron_set = MagicMock()
        neuron_set.expand_multi_values.return_value = [neuron_set]
        neuron_set.get_neuron_ids.return_value = {}

        with pytest.raises(ValueError, match="resolved to no node IDs"):
            _stage_circuit_for_neuron_set_resolution(
                db_client=mock_db_client,
                circuit_id=circuit_id,
                circuit_entity=circuit_entity,
                asset=asset,
                neuron_set=neuron_set,
            )

    def test_raises_when_model_template_missing(self, mock_db_client):
        """Missing model_template attribute raises ValueError."""
        circuit_id = str(uuid4())
        circuit_entity, asset = _get_circuit_asset(mock_db_client, circuit_id)

        neuron_set = MagicMock()
        neuron_set.expand_multi_values.return_value = [neuron_set]
        neuron_set.get_neuron_ids.return_value = {"S1nonbarrel_neurons": [0, 1]}

        with patch(
            "obi_one.scientific.library.neuronal_manipulation_properties.NodeStorage"
        ) as mock_ns:
            mock_pop = MagicMock()
            mock_pop.attribute_names = ["x", "y"]
            mock_ns.return_value.open_population.return_value = mock_pop

            with pytest.raises(ValueError, match="model_template"):
                _stage_circuit_for_neuron_set_resolution(
                    db_client=mock_db_client,
                    circuit_id=circuit_id,
                    circuit_entity=circuit_entity,
                    asset=asset,
                    neuron_set=neuron_set,
                )


class TestGetCircuitManipulationPropertiesFastPath:
    """Tests for get_circuit_manipulation_properties with neuron_set=None (fast path)."""

    def test_fast_path_with_derivations(self, mock_db_client):
        """Unreadable circuit files: every derivation is used and the intersection computed."""
        client = mock_db_client
        client.fetch_file.side_effect = EntitySDKError("storage unavailable")
        emodel_id_1 = str(uuid4())
        emodel_id_2 = str(uuid4())

        deriv1 = MagicMock()
        deriv1.label = "hoc:cACint_L23MC"
        deriv1.used.id = emodel_id_1
        deriv2 = MagicMock()
        deriv2.label = "hoc:cADpyr_L6BPC"
        deriv2.used.id = emodel_id_2
        client.search_entity.return_value.all.return_value = [deriv1, deriv2]

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

            result = get_circuit_manipulation_properties(
                db_client=client,
                circuit_id=str(uuid4()),
                neuron_set=None,
            )

        assert result["entity_type"] == "circuit"
        assert result["populations"] is None
        assert "MechanismVariablesByIonChannel" in result
        assert "NaTg" in result["MechanismVariablesByIonChannel"]
        assert all("emodel_circuit derivation instead" in w for w in result["warnings"])

    def test_fast_path_no_derivations(self, mock_db_client):
        """Unreadable circuit files and no derivations: empty response with a warning."""
        client = mock_db_client
        client.fetch_file.side_effect = EntitySDKError("storage unavailable")
        client.search_entity.return_value.all.return_value = []

        result = get_circuit_manipulation_properties(
            db_client=client,
            circuit_id=str(uuid4()),
            neuron_set=None,
        )

        assert result["entity_type"] == "circuit"
        assert result["MechanismVariablesByIonChannel"] == {}
        assert result["warnings"] == [
            (
                "Circuit files not readable (EntitySDKError)."
                " No emodel_circuit derivations found for this circuit."
            )
        ]

    def test_fast_path_rejects_a_malformed_circuit_like_the_neuron_set_path(self):
        """A circuit without one sonata_circuit asset is a 400 in both modes."""
        client = MagicMock()
        client.get_entity.return_value.assets = []
        with pytest.raises(ValueError, match="exactly one sonata_circuit"):
            get_circuit_manipulation_properties(
                db_client=client, circuit_id=str(uuid4()), neuron_set=None
            )
        client.search_entity.assert_not_called()


class TestMultiPopulationRegression:
    """Regression tests for multi-population correctness gaps."""

    def test_collision_same_node_id_different_populations(self, mock_db_client):
        """Two populations with same node ID 0 but different templates both contribute.

        Before the fix, node_to_template was keyed by int node_id only, so
        pop_B's template overwrote pop_A's entry for node 0. This test verifies
        both emodels are present in the intersection.
        """
        circuit_id = str(uuid4())
        emodel_id_1 = str(uuid4())
        emodel_id_2 = str(uuid4())

        deriv1 = MagicMock()
        deriv1.label = "hoc:cADpyr_L5TPC"
        deriv1.used.id = emodel_id_1
        deriv2 = MagicMock()
        deriv2.label = "hoc:bAC_L6BTC"
        deriv2.used.id = emodel_id_2
        mock_db_client.search_entity.return_value.all.return_value = [deriv1, deriv2]

        # Both populations have node ID 0, but different model_templates
        mock_templates = {
            ("pop_A", 0): "hoc:cADpyr_L5TPC",
            ("pop_B", 0): "hoc:bAC_L6BTC",
        }
        neuron_set = MagicMock()
        neuron_set.expand_multi_values.return_value = [neuron_set]

        with (
            patch(
                "obi_one.scientific.library.neuronal_manipulation_properties"
                "._stage_circuit_for_neuron_set_resolution",
                return_value=(["pop_A", "pop_B"], mock_templates, {}),
            ),
            patch(
                "obi_one.scientific.library.neuronal_manipulation_properties"
                ".get_mechanism_variables_for_emodel"
            ) as mock_get_vars,
        ):
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

        # Both emodels should have been fetched (2 calls)
        assert mock_get_vars.call_count == 2
        # NaTg is common to both -> should appear in intersection
        assert "NaTg" in result["MechanismVariablesByIonChannel"]
        assert all("emodel_circuit derivation instead" in w for w in result["warnings"])

    def test_empty_node_id_lists_rejected(self, mock_db_client):
        """Neuron set returning {"pop": []} raises ValueError, not silent empty.

        Before the fix, the empty check only caught {} but not a non-empty
        dict with all-empty node-ID lists. This caused a silent empty response.
        """
        circuit_id = str(uuid4())
        circuit_entity, asset = _get_circuit_asset(mock_db_client, circuit_id)

        neuron_set = MagicMock()
        neuron_set.expand_multi_values.return_value = [neuron_set]
        neuron_set.get_neuron_ids.return_value = {"S1nonbarrel_neurons": []}

        with pytest.raises(ValueError, match="resolved to no node IDs"):
            _stage_circuit_for_neuron_set_resolution(
                db_client=mock_db_client,
                circuit_id=circuit_id,
                circuit_entity=circuit_entity,
                asset=asset,
                neuron_set=neuron_set,
            )

    def test_all_populations_empty_rejected(self, mock_db_client):
        """Multiple populations all with empty lists also raises ValueError."""
        circuit_id = str(uuid4())
        circuit_entity, asset = _get_circuit_asset(mock_db_client, circuit_id)

        neuron_set = MagicMock()
        neuron_set.expand_multi_values.return_value = [neuron_set]
        neuron_set.get_neuron_ids.return_value = {
            "pop_A": [],
            "pop_B": [],
        }

        with pytest.raises(ValueError, match="resolved to no node IDs"):
            _stage_circuit_for_neuron_set_resolution(
                db_client=mock_db_client,
                circuit_id=circuit_id,
                circuit_entity=circuit_entity,
                asset=asset,
                neuron_set=neuron_set,
            )


class TestMemodelMechanismVariableResponse:
    """Tests for the strict MEModel mechanism-variable helper and response grouping."""

    def test_section_properties_use_channel_sections_and_group_values(self):
        mapping = ChannelSectionListMapping(
            channel_to_section_lists={
                "NaTg": ChannelInfo(
                    section_lists=["somatic", "axonal"],
                    entity_id="channel-id",
                )
            }
        )
        variables = [
            MechanismVariable(
                neuron_variable="cm",
                channel_name="-",
                section_list="somatic",
                units="uF/cm2",
                limits=[0.0, 10.0],
                variable_type="RANGE",
            ),
            MechanismVariable(
                neuron_variable="Ra",
                channel_name="-",
                section_list="axonal",
                units="ohm-cm",
                limits=[0.0, 1000.0],
                variable_type="RANGE",
            ),
            MechanismVariable(
                neuron_variable="gNaTgbar_NaTg",
                channel_name="NaTg",
                section_list="somatic",
                value=0.1,
                limits=[0.0, 10.0],
                variable_type="RANGE",
            ),
            MechanismVariable(
                neuron_variable="gNaTgbar_NaTg",
                channel_name="NaTg",
                section_list="axonal",
                value=0.2,
                limits=[0.0, 10.0],
                variable_type="RANGE",
            ),
        ]

        result = _build_mechanism_variables_by_ion_channel_response(variables, mapping)

        assert result["-"].entity_id is None
        assert set(result["-"].section_lists) == {"somatic", "axonal"}
        assert result["-"].variables["cm"].section_lists_original_values == {"somatic": None}
        assert result["NaTg"].entity_id == "channel-id"
        assert result["NaTg"].variables["gNaTgbar_NaTg"].section_lists_original_values == {
            "somatic": 0.1,
            "axonal": 0.2,
        }

    def test_section_properties_without_mapping_use_default_sections(self):
        variable = MechanismVariable(
            neuron_variable="cm",
            channel_name="-",
            section_list="somatic",
            variable_type="RANGE",
        )

        result = _build_mechanism_variables_by_ion_channel_response(
            [variable], ChannelSectionListMapping(channel_to_section_lists={})
        )

        assert set(result["-"].section_lists) == {"somatic", "apical", "basal", "axonal"}

    def test_strict_helper_fetches_and_groups_mechanism_variables(self):
        db_client = MagicMock()
        memodel = MagicMock()
        db_client.get_entity.return_value = memodel
        variables = [
            MechanismVariable(
                neuron_variable="gNaTgbar_NaTg",
                channel_name="NaTg",
                section_list="somatic",
                value=0.1,
                limits=[0.0, 10.0],
                variable_type="RANGE",
            )
        ]
        mapping = ChannelSectionListMapping(
            channel_to_section_lists={
                "NaTg": ChannelInfo(section_lists=["somatic"], entity_id="channel-id")
            }
        )

        with patch(
            "obi_one.scientific.library.memodel_circuit.get_mechanism_variables",
            return_value=(variables, mapping),
        ) as mock_get:
            result = get_memodel_mechanism_variables(db_client, "memodel-id")

        db_client.get_entity.assert_called_once()
        mock_get.assert_called_once_with(db_client, memodel)
        assert result["NaTg"].entity_id == "channel-id"
        assert result["NaTg"].variables["gNaTgbar_NaTg"].section_lists_original_values == {
            "somatic": 0.1
        }

    def test_strict_helper_propagates_entity_fetch_errors(self):
        db_client = MagicMock()
        db_client.get_entity.side_effect = RuntimeError("fetch failed")

        with pytest.raises(RuntimeError, match="fetch failed"):
            get_memodel_mechanism_variables(db_client, "memodel-id")


class TestMEModelCircuitValidation:
    """Tests for single-neuron validation on MEModel circuit wrappers."""

    @staticmethod
    def _fake_snap_circuit(*, node_ids, edge_population_names=None, populations=None):
        nodes = MagicMock()
        nodes.ids.return_value = node_ids
        nodes.population_names = list(populations or {})
        nodes.__getitem__.side_effect = (populations or {}).__getitem__
        edges = SimpleNamespace(population_names=edge_population_names or [])
        return SimpleNamespace(nodes=nodes, edges=edges)

    def test_me_model_circuit_rejects_multiple_neurons(self, monkeypatch):
        fake_circuit = self._fake_snap_circuit(node_ids=[0, 1])
        monkeypatch.setattr(circuit_module.snap, "Circuit", lambda _path: fake_circuit)
        circuit = MEModelCircuit.model_construct(name="me-model", path="circuit.json")

        with pytest.raises(OBIONEError, match="exactly one neuron"):
            circuit.confirm_single_neuron_without_synapses()

    def test_me_model_circuit_rejects_synapses(self, monkeypatch):
        fake_circuit = self._fake_snap_circuit(node_ids=[0], edge_population_names=["synapses"])
        monkeypatch.setattr(circuit_module.snap, "Circuit", lambda _path: fake_circuit)
        circuit = MEModelCircuit.model_construct(name="me-model", path="circuit.json")

        with pytest.raises(OBIONEError, match="must not contain any synapses"):
            circuit.confirm_single_neuron_without_synapses()

    def test_me_model_with_synapses_circuit_rejects_multiple_real_neurons(self, monkeypatch):
        populations = {
            "real": SimpleNamespace(type="biophysical", size=2),
            "virtual": SimpleNamespace(type="virtual", size=10),
        }
        fake_circuit = self._fake_snap_circuit(node_ids=[0, 1], populations=populations)
        monkeypatch.setattr(circuit_module.snap, "Circuit", lambda _path: fake_circuit)
        circuit = MEModelWithSynapsesCircuit.model_construct(
            name="me-model-with-synapses", path="circuit.json"
        )

        with pytest.raises(OBIONEError, match="exactly one neuron"):
            circuit.confirm_single_neuron()


class TestVariablesReadFromCircuitFiles:
    """End to end on the tiny circuit: hoc and mod files replace the derivation lookup."""

    def test_neuron_set_path_needs_no_derivation(self, mock_db_client):
        neuron_set = MagicMock()
        neuron_set.expand_multi_values.return_value = [neuron_set]
        # One node, so one template: the response keeps that template's own values.
        neuron_set.get_neuron_ids.return_value = {"S1nonbarrel_neurons": [0]}

        result = get_circuit_manipulation_properties(
            db_client=mock_db_client, circuit_id=str(uuid4()), neuron_set=neuron_set
        )

        assert _searches(mock_db_client, DerivationModel) == []
        assert result["populations"] == ["S1nonbarrel_neurons"]
        assert result["warnings"] is None
        channels = result["MechanismVariablesByIonChannel"]
        assert {"pas", "NaTg", "-"} <= set(channels)
        g_pas = channels["pas"].variables["g_pas"].section_lists_original_values
        assert all(value is not None for value in g_pas.values())

    def test_no_neuron_set_reads_every_template(self, mock_db_client):
        result = get_circuit_manipulation_properties(
            db_client=mock_db_client, circuit_id=str(uuid4()), neuron_set=None
        )

        assert _searches(mock_db_client, DerivationModel) == []
        assert result["populations"] is None
        assert result["warnings"] is None
        assert "NaTg" in result["MechanismVariablesByIonChannel"]

    @pytest.mark.parametrize("node_ids", [None, [0]])
    def test_one_listing_per_request(self, mock_db_client, node_ids):
        """The listing gives both the nodes.h5 sizes and the mod files."""
        neuron_set = None
        if node_ids is not None:
            neuron_set = MagicMock()
            neuron_set.expand_multi_values.return_value = [neuron_set]
            neuron_set.get_neuron_ids.return_value = {"S1nonbarrel_neurons": node_ids}
        get_circuit_manipulation_properties(
            db_client=mock_db_client, circuit_id=str(uuid4()), neuron_set=neuron_set
        )
        mock_db_client.list_directory.assert_called_once()

    def test_no_neuron_set_reads_nodes_by_ranges_although_storage_refuses_head(
        self, mock_db_client
    ):
        """The test storage answers HEAD with 403, as S3 does on presigned GET URLs."""
        get_circuit_manipulation_properties(
            db_client=mock_db_client, circuit_id=str(uuid4()), neuron_set=None
        )
        nodes_fetches = [
            c.kwargs["strategy"]
            for c in mock_db_client.fetch_file.call_args_list
            if str(c.kwargs["asset_path"]).endswith("nodes.h5")
        ]
        assert nodes_fetches == [FetchFileStrategy.link_only]  # the probe only, no download

    def test_listing_failure_downloads_nodes_and_reports_the_templates(self, mock_db_client):
        mock_db_client.list_directory.side_effect = EntitySDKError("HTTP error 503")
        mock_db_client.search_entity.return_value.all.return_value = []
        result = get_circuit_manipulation_properties(
            db_client=mock_db_client, circuit_id=str(uuid4()), neuron_set=None
        )
        nodes_fetches = [
            c.kwargs["strategy"]
            for c in mock_db_client.fetch_file.call_args_list
            if str(c.kwargs["asset_path"]).endswith("nodes.h5")
        ]
        assert nodes_fetches == [FetchFileStrategy.link_only, FetchFileStrategy.link_or_download]
        assert any("files not readable (EntitySDKError)" in w for w in result["warnings"])

    def test_unreadable_template_falls_back_to_derivation(self, mock_db_client):
        """A hoc file that is not template output is reported and read from the database."""
        mock_db_client.search_entity.return_value.all.return_value = []
        neuron_set = MagicMock()
        neuron_set.expand_multi_values.return_value = [neuron_set]
        neuron_set.get_neuron_ids.return_value = {"S1nonbarrel_neurons": [0, 1, 2]}
        original = mock_db_client.fetch_file.side_effect

        def _fetch_file(*, output_path, asset_path, **kwargs):
            original(output_path=output_path, asset_path=asset_path, **kwargs)
            if Path(asset_path).name == "cADpyr_L6BPC.hoc":
                text = Path(output_path).read_text(encoding="utf-8")
                Path(output_path).write_text(
                    text.replace("    Ra = 100\n", "    Ra = x\n"), encoding="utf-8"
                )

        mock_db_client.fetch_file.side_effect = _fetch_file

        result = get_circuit_manipulation_properties(
            db_client=mock_db_client, circuit_id=str(uuid4()), neuron_set=neuron_set
        )

        assert len(_searches(mock_db_client, DerivationModel)) == 1
        assert any(
            "No derivation found for model_template: hoc:cADpyr_L6BPC" in w
            for w in result["warnings"]
        )
        # The other template was still read from its files.
        assert "NaTg" in result["MechanismVariablesByIonChannel"]


class TestCircuitFileSafety:
    """Guards for paths and file content that come from user-registered circuits."""

    @pytest.mark.parametrize("asset_path", ["../outside.hoc", "emodels_hoc/../../x.hoc", "/etc/x"])
    def test_stage_file_refuses_paths_outside_the_asset(self, tmp_path, asset_path):
        client = MagicMock()
        with pytest.raises(ValueError, match="outside the circuit"):
            _stage_file(client, str(uuid4()), _asset(), tmp_path, asset_path)
        client.fetch_file.assert_not_called()

    def test_oversized_model_file_is_refused(self, tmp_path):
        big = tmp_path / "big.hoc"
        big.write_bytes(b"x" * (MAX_MODEL_FILE_BYTES + 1))
        with pytest.raises(HocTemplateError, match="byte limit"):
            _read_model_file(big)

    def test_fetch_errors_do_not_reach_the_response(self):
        err = RuntimeError("https://bucket.s3.amazonaws.com/x?X-Amz-Security-Token=secret")
        assert "secret" not in _public_reason(err)
        assert _public_reason(HocTemplateError("unexpected line")) == "unexpected line"

    def test_template_name_with_traversal_falls_back(self, mock_db_client):
        mock_db_client.search_entity.return_value.all.return_value = []
        neuron_set = MagicMock()
        neuron_set.expand_multi_values.return_value = [neuron_set]
        neuron_set.get_neuron_ids.return_value = {"S1nonbarrel_neurons": [0]}
        with patch(
            "obi_one.scientific.library.neuronal_manipulation_properties.NodeStorage"
        ) as mock_ns:
            pop = MagicMock()
            pop.attribute_names = ["model_template"]
            pop.get_attribute.return_value = ["hoc:../../../escape"]
            mock_ns.return_value.open_population.return_value = pop
            result = get_circuit_manipulation_properties(
                db_client=mock_db_client, circuit_id=str(uuid4()), neuron_set=neuron_set
            )
        assert result["MechanismVariablesByIonChannel"] == {}
        assert any("hoc:../../../escape" in w for w in result["warnings"])
        fetched = [str(c.kwargs["asset_path"]) for c in mock_db_client.fetch_file.call_args_list]
        assert not any("escape" in path for path in fetched)


SINGLE_NEURON_CIRCUIT_DIR = Path(
    "examples/data/single_neuron_circuits/SingleNeuronCircuit__top_nodes_dim6__IDX1"
)


def _copying_client(circuit_dir: Path, failing: set[str] = frozenset()) -> MagicMock:
    """A db_client whose fetch_file copies from circuit_dir.

    Paths in ``failing`` or absent from ``circuit_dir`` raise ``EntitySDKError``, as
    entitysdk does for an HTTP 404.
    """
    copy = _make_fetch_file_side_effect(circuit_dir)

    def _fetch_file(*, output_path, asset_path, **kwargs):
        if str(asset_path) in failing or not (circuit_dir / asset_path).exists():
            msg = f"HTTP error 404 for {asset_path}"
            raise EntitySDKError(msg)
        copy(output_path=output_path, asset_path=asset_path, **kwargs)

    client = MagicMock()
    client.fetch_file.side_effect = _fetch_file
    client.list_directory.return_value = _listing(circuit_dir)
    _serve_storage(client, circuit_dir)
    return client


def _searches(client: MagicMock, entity_type: type) -> list:
    """The ``search_entity`` calls of one entity type."""
    return [
        c for c in client.search_entity.call_args_list if c.kwargs["entity_type"] is entity_type
    ]


def _asset() -> MagicMock:
    """A sonata_circuit directory asset as the circuit entity holds it."""
    return MagicMock(id=uuid4(), is_directory=True)


def _read_models(client, tmp_path, templates, dirs):
    return _read_template_models(
        client,
        str(uuid4()),
        _asset(),
        tmp_path,
        {"S1nonbarrel_neurons": templates},
        {"S1nonbarrel_neurons": dirs},
        _asset_files(client, str(uuid4()), _asset()),
    )


class TestCircuitFileStagingEdges:
    def test_stage_file_reuses_an_already_staged_file(self, tmp_path):
        (tmp_path / "circuit_config.json").write_text("{}")
        client = MagicMock()
        path = _stage_file(client, str(uuid4()), _asset(), tmp_path, "circuit_config.json")
        assert path == tmp_path / "circuit_config.json"
        client.fetch_file.assert_not_called()

    def test_fetch_file_gets_the_asset_object_not_its_id(self, tmp_path):
        """With an id, entitysdk fetches the asset metadata again before every file."""
        client = MagicMock()
        asset = _asset()
        _stage_file(client, str(uuid4()), asset, tmp_path, "circuit_config.json")
        assert client.fetch_file.call_args.kwargs["asset_id"] is asset

    def test_listing_uses_the_asset_id(self, tmp_path):
        client = _copying_client(SINGLE_NEURON_CIRCUIT_DIR)
        asset = _asset()
        _read_template_models(
            client,
            str(uuid4()),
            asset,
            tmp_path,
            {"S1nonbarrel_neurons": {"hoc:cADpyr_L6BPC"}},
            {"S1nonbarrel_neurons": PopulationModelDirs("biophysical", "emodels_hoc", ("mod",))},
            _asset_files(client, str(uuid4()), asset),
        )
        assert client.list_directory.call_args.kwargs["asset_id"] == asset.id
        assert all(c.kwargs["asset_id"] is asset for c in client.fetch_file.call_args_list)

    @pytest.mark.parametrize("value", [None, ""])
    def test_relative_dir_is_none_when_unset(self, tmp_path, value):
        assert _relative_dir(value, tmp_path) is None

    def test_relative_dir_is_none_outside_the_asset(self, tmp_path):
        assert _relative_dir(str(tmp_path.parent / "elsewhere"), tmp_path) is None
        assert _relative_dir(str(tmp_path / "mod"), tmp_path) == "mod"

    def test_missing_node_sets_json_is_tolerated(self, tmp_path):
        client = _copying_client(TINY_CIRCUIT_DIR, failing={"node_sets.json"})
        config_path, nodes, _dirs = _stage_circuit_for_neuron_set(
            client, str(uuid4()), _asset(), tmp_path
        )
        assert config_path.exists()
        assert not (tmp_path / "node_sets.json").exists()
        assert all((tmp_path / path).exists() for path in nodes.values())

    def test_population_types_limit_which_nodes_files_are_staged(self, tmp_path):
        client = _copying_client(TINY_CIRCUIT_DIR)
        _config, nodes, dirs = _stage_circuit_for_neuron_set(
            client, str(uuid4()), _asset(), tmp_path, population_types=["biophysical"]
        )
        assert set(nodes) == {"S1nonbarrel_neurons"}
        assert {"POm", "VPM"} <= set(dirs)  # directories known for every population
        fetched = {str(c.kwargs["asset_path"]) for c in client.fetch_file.call_args_list}
        assert not any(path.startswith(("POm", "VPM")) for path in fetched)

    def test_undeclared_mechanisms_dir_gets_the_candidate_order(self, tmp_path):
        client = _copying_client(SINGLE_NEURON_CIRCUIT_DIR)  # mechanisms_dir is ""
        _config, _nodes, dirs = _stage_circuit_for_neuron_set(
            client, str(uuid4()), _asset(), tmp_path
        )
        assert dirs["S1nonbarrel_neurons"].mod_dirs == UNDECLARED_MOD_DIRS
        assert UNDECLARED_MOD_DIRS[0] == "mod"


class TestReadTemplateModelsFailures:
    HOC_TEMPLATE = "hoc:cADpyr_L6BPC"

    def test_population_without_hoc_dir(self, tmp_path):
        client = _copying_client(SINGLE_NEURON_CIRCUIT_DIR)
        models = _read_models(
            client,
            tmp_path,
            {self.HOC_TEMPLATE},
            PopulationModelDirs(population_type="biophysical", hoc_dir=None, mod_dirs=("mod",)),
        )
        assert models == {self.HOC_TEMPLATE: "population has no biophysical_neuron_models_dir"}
        client.fetch_file.assert_not_called()

    @pytest.mark.parametrize("mod_folder", ["mod", "mechanisms"])
    def test_undeclared_mod_dir_is_found_in_the_listing(self, tmp_path, mod_folder):
        """Mod files in ``mod/`` (OBI circuits) or ``mechanisms/`` (entitysdk MEModels)."""
        circuit_dir = tmp_path / "circuit"
        shutil.copytree(SINGLE_NEURON_CIRCUIT_DIR / "emodels_hoc", circuit_dir / "emodels_hoc")
        shutil.copytree(SINGLE_NEURON_CIRCUIT_DIR / "mod", circuit_dir / mod_folder)
        client = _copying_client(circuit_dir)
        models = _read_models(
            client,
            tmp_path / "staged",
            {self.HOC_TEMPLATE},
            PopulationModelDirs("biophysical", hoc_dir="emodels_hoc", mod_dirs=UNDECLARED_MOD_DIRS),
        )
        assert isinstance(models[self.HOC_TEMPLATE], TemplateModel)
        client.list_directory.assert_called_once()
        fetched = {str(c.kwargs["asset_path"]) for c in client.fetch_file.call_args_list}
        assert all(path.startswith((f"{mod_folder}/", "emodels_hoc/")) for path in fetched)
        # The whole directory is read, not one probe per mechanism.
        assert len([p for p in fetched if p.endswith(".mod")]) == len(
            list((circuit_dir / mod_folder).glob("*.mod"))
        )

    def test_mod_file_named_differently_from_its_suffix(self, tmp_path):
        """rCA1 keeps ``kdrb`` in ``kdrbca1.mod``: the SUFFIX decides, not the file name."""
        circuit_dir = tmp_path / "circuit"
        shutil.copytree(SINGLE_NEURON_CIRCUIT_DIR / "emodels_hoc", circuit_dir / "emodels_hoc")
        shutil.copytree(SINGLE_NEURON_CIRCUIT_DIR / "mod", circuit_dir / "mod")
        (circuit_dir / "mod" / "NaTg.mod").rename(circuit_dir / "mod" / "natg_v2.mod")
        client = _copying_client(circuit_dir)
        models = _read_models(
            client,
            tmp_path / "staged",
            {self.HOC_TEMPLATE},
            PopulationModelDirs("biophysical", hoc_dir="emodels_hoc", mod_dirs=("mod",)),
        )
        model = models[self.HOC_TEMPLATE]
        assert isinstance(model, TemplateModel)
        assert model.mechanisms["NaTg"].suffix == "NaTg"

    def test_mod_file_without_a_suffix_is_ignored(self, tmp_path):
        """A mod file that defines no mechanism (no SUFFIX) does not fail the templates."""
        circuit_dir = tmp_path / "circuit"
        shutil.copytree(SINGLE_NEURON_CIRCUIT_DIR / "emodels_hoc", circuit_dir / "emodels_hoc")
        shutil.copytree(SINGLE_NEURON_CIRCUIT_DIR / "mod", circuit_dir / "mod")
        (circuit_dir / "mod" / "helper.mod").write_text("NEURON {\n\tGLOBAL x\n}\n")
        client = _copying_client(circuit_dir)
        models = _read_models(
            client,
            tmp_path / "staged",
            {self.HOC_TEMPLATE},
            PopulationModelDirs("biophysical", hoc_dir="emodels_hoc", mod_dirs=("mod",)),
        )
        assert isinstance(models[self.HOC_TEMPLATE], TemplateModel)

    def test_mechanism_without_a_mod_file_fails_the_template(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        shutil.copytree(SINGLE_NEURON_CIRCUIT_DIR / "emodels_hoc", circuit_dir / "emodels_hoc")
        shutil.copytree(SINGLE_NEURON_CIRCUIT_DIR / "mod", circuit_dir / "mod")
        (circuit_dir / "mod" / "NaTg.mod").unlink()
        client = _copying_client(circuit_dir)
        models = _read_models(
            client,
            tmp_path / "staged",
            {self.HOC_TEMPLATE},
            PopulationModelDirs("biophysical", hoc_dir="emodels_hoc", mod_dirs=("mod",)),
        )
        assert models == {self.HOC_TEMPLATE: "no mod file in the circuit defines mechanism 'NaTg'"}

    def test_mechanism_defined_twice_fails_the_template(self, tmp_path):
        """NEURON refuses two files with one SUFFIX; the reader does not pick one."""
        circuit_dir = tmp_path / "circuit"
        shutil.copytree(SINGLE_NEURON_CIRCUIT_DIR / "emodels_hoc", circuit_dir / "emodels_hoc")
        shutil.copytree(SINGLE_NEURON_CIRCUIT_DIR / "mod", circuit_dir / "mod")
        shutil.copy(circuit_dir / "mod" / "NaTg.mod", circuit_dir / "mod" / "NaTg_copy.mod")
        client = _copying_client(circuit_dir)
        models = _read_models(
            client,
            tmp_path / "staged",
            {self.HOC_TEMPLATE},
            PopulationModelDirs("biophysical", hoc_dir="emodels_hoc", mod_dirs=("mod",)),
        )
        assert models == {
            self.HOC_TEMPLATE: "mechanism 'NaTg' is defined by more than one mod file"
        }

    def test_mod_file_in_no_candidate_dir_fails_the_template(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        shutil.copytree(SINGLE_NEURON_CIRCUIT_DIR / "emodels_hoc", circuit_dir / "emodels_hoc")
        client = _copying_client(circuit_dir)
        models = _read_models(
            client,
            tmp_path / "staged",
            {self.HOC_TEMPLATE},
            PopulationModelDirs("biophysical", hoc_dir="emodels_hoc", mod_dirs=UNDECLARED_MOD_DIRS),
        )
        assert models == {
            self.HOC_TEMPLATE: "no mod file in the circuit defines mechanism 'CaDynamics_DC0'"
        }

    def test_listing_failure_fails_every_template(self, tmp_path):
        client = _copying_client(SINGLE_NEURON_CIRCUIT_DIR)
        client.list_directory.side_effect = EntitySDKError("HTTP error 503")
        models = _read_models(
            client,
            tmp_path,
            {self.HOC_TEMPLATE},
            PopulationModelDirs("biophysical", hoc_dir="emodels_hoc", mod_dirs=("mod",)),
        )
        assert models == {self.HOC_TEMPLATE: "files not readable (EntitySDKError)"}
        client.fetch_file.assert_not_called()

    def test_hoc_fetch_failure_is_reported_by_type_only(self, tmp_path):
        client = _copying_client(
            SINGLE_NEURON_CIRCUIT_DIR, failing={"emodels_hoc/cADpyr_L6BPC.hoc"}
        )
        models = _read_models(
            client,
            tmp_path,
            {self.HOC_TEMPLATE},
            PopulationModelDirs("biophysical", hoc_dir="emodels_hoc", mod_dirs=("mod",)),
        )
        assert models == {self.HOC_TEMPLATE: "files not readable (EntitySDKError)"}

    def test_mod_fetch_failure_fails_only_that_template(self, tmp_path):
        client = _copying_client(SINGLE_NEURON_CIRCUIT_DIR, failing={"mod/NaTg.mod"})
        models = _read_models(
            client,
            tmp_path,
            {self.HOC_TEMPLATE},
            PopulationModelDirs("biophysical", hoc_dir="emodels_hoc", mod_dirs=("mod",)),
        )
        assert models == {self.HOC_TEMPLATE: "files not readable (EntitySDKError)"}

    def test_all_files_read(self, tmp_path):
        client = _copying_client(SINGLE_NEURON_CIRCUIT_DIR)
        models = _read_models(
            client,
            tmp_path,
            {self.HOC_TEMPLATE},
            PopulationModelDirs("biophysical", hoc_dir="emodels_hoc", mod_dirs=("mod",)),
        )
        model = models[self.HOC_TEMPLATE]
        assert isinstance(model, TemplateModel)
        assert set(model.mechanisms) == model.biophysics.mod_file_mechanisms
        assert "pas" in model.biophysics.inserted_mechanisms


class TestUniqueTemplates:
    @pytest.mark.parametrize(
        ("circuit_dir", "enumerated"),
        [(TINY_CIRCUIT_DIR, True), (SINGLE_NEURON_CIRCUIT_DIR, False)],
    )
    def test_enumerated_and_plain_columns_give_the_same_set(self, circuit_dir, enumerated):
        population = "S1nonbarrel_neurons"
        nodes = circuit_dir / population / "nodes.h5"
        pop = NodeStorage(str(nodes)).open_population(population)
        assert ("model_template" in pop.enumeration_names) is enumerated
        expected = {t for t in pop.get_attribute("model_template", pop.select_all()) if t}
        with h5py.File(nodes, "r") as h5:
            assert _unique_templates(h5[f"nodes/{population}/0"]) == expected


def _circuit_without_model_template(tmp_path: Path) -> Path:
    circuit_dir = tmp_path / "circuit"
    shutil.copytree(TINY_CIRCUIT_DIR, circuit_dir)
    with h5py.File(circuit_dir / "S1nonbarrel_neurons" / "nodes.h5", "r+") as h5:
        group = h5["nodes/S1nonbarrel_neurons/0"]
        del group["model_template"]
        del group["@library/model_template"]
    return circuit_dir


class TestNoNeuronSetWithoutTemplates:
    def test_circuit_without_model_template_returns_a_warning(self, tmp_path):
        client = _copying_client(_circuit_without_model_template(tmp_path))
        client.get_entity.return_value = _sonata_entity()
        result = get_circuit_manipulation_properties(
            db_client=client, circuit_id=str(uuid4()), neuron_set=None
        )
        assert result["MechanismVariablesByIonChannel"] == {}
        assert result["warnings"] == ["No population with a model_template found in this circuit."]


class TestPopulationTemplatesReadPath:
    """Without a neuron set, model_template is read with as little transfer as possible."""

    POPULATION = "S1nonbarrel_neurons"
    NODES = "S1nonbarrel_neurons/nodes.h5"

    @staticmethod
    def _expected(circuit_dir: Path) -> set[str]:
        pop = NodeStorage(str(circuit_dir / "S1nonbarrel_neurons/nodes.h5")).open_population(
            "S1nonbarrel_neurons"
        )
        return {t for t in pop.get_attribute("model_template", pop.select_all()) if t}

    def _read(self, client, tmp_path):
        files = _asset_files(client, str(uuid4()), _asset())
        return _population_templates(
            client,
            str(uuid4()),
            _asset(),
            tmp_path / "staged",
            self.POPULATION,
            self.NODES,
            None if isinstance(files, Exception) else files.get(self.NODES),
        )

    def test_mounted_store_links_the_file_and_makes_no_http_request(self, tmp_path):
        client = MagicMock()
        client.fetch_file.side_effect = _make_link_or_copy_fetch_file_side_effect(
            TINY_CIRCUIT_DIR.resolve()
        )
        assert self._read(client, tmp_path) == self._expected(TINY_CIRCUIT_DIR)
        assert client.fetch_file.call_args.kwargs["strategy"] == FetchFileStrategy.link_only
        client._http_client.get.assert_not_called()

    def test_without_a_store_only_byte_ranges_are_read(self, tmp_path):
        client = _copying_client(TINY_CIRCUIT_DIR)
        assert self._read(client, tmp_path) == self._expected(TINY_CIRCUIT_DIR)
        strategies = [c.kwargs["strategy"] for c in client.fetch_file.call_args_list]
        assert strategies == [FetchFileStrategy.link_only]  # the probe only, no download

    def test_unknown_size_downloads_without_trying_ranges(self, tmp_path, caplog):
        """A failed listing gives no size: the file is downloaded, storage is not asked."""
        client = _copying_client(TINY_CIRCUIT_DIR)
        client.list_directory.side_effect = EntitySDKError("HTTP error 503")
        client._http_client = MagicMock()
        assert self._read(client, tmp_path) == self._expected(TINY_CIRCUIT_DIR)
        strategies = [c.kwargs["strategy"] for c in client.fetch_file.call_args_list]
        assert strategies == [FetchFileStrategy.link_only, FetchFileStrategy.link_or_download]
        client._http_client.get.assert_not_called()
        assert "Partial read" not in caplog.text

    def test_storage_without_ranges_falls_back_to_the_download(self, tmp_path, caplog):
        client = _copying_client(TINY_CIRCUIT_DIR)
        _serve_storage(client, TINY_CIRCUIT_DIR, redirect=False)
        assert self._read(client, tmp_path) == self._expected(TINY_CIRCUIT_DIR)
        strategies = [c.kwargs["strategy"] for c in client.fetch_file.call_args_list]
        assert strategies == [FetchFileStrategy.link_only, FetchFileStrategy.link_or_download]
        assert "Partial read of S1nonbarrel_neurons/nodes.h5 failed" in caplog.text

    @pytest.mark.parametrize("redirect", [True, False])
    def test_population_without_model_template_is_none_on_both_paths(self, tmp_path, redirect):
        circuit_dir = _circuit_without_model_template(tmp_path)
        client = _copying_client(circuit_dir)
        _serve_storage(client, circuit_dir, redirect=redirect)
        assert self._read(client, tmp_path) is None

    def test_plain_string_column_is_read_remotely(self, tmp_path):
        """The single-neuron circuits store model_template as strings, not an enumeration."""
        client = _copying_client(SINGLE_NEURON_CIRCUIT_DIR)
        assert self._read(client, tmp_path) == self._expected(SINGLE_NEURON_CIRCUIT_DIR)
        assert [c.kwargs["strategy"] for c in client.fetch_file.call_args_list] == [
            FetchFileStrategy.link_only
        ]


def _entity(range_units: dict, global_units: dict | None = None) -> SimpleNamespace:
    """An ion channel model entity as far as its units go."""
    return SimpleNamespace(
        neuron_block=SimpleNamespace(
            range=[{name: unit} for name, unit in range_units.items()],
            global_=[{name: unit} for name, unit in (global_units or {}).items()],
        )
    )


def _kmb() -> ModMechanism:
    """rCA1's kmb.mod: gbar has a unit, sh and tau none, ik is a current."""
    return ModMechanism(
        suffix="kmb", range_variables=["gbar", "ik", "sh", "tau"], units={"gbar": "mho/cm2"}
    )


class TestUnitsFromTheDatabase:
    """Units a circuit's mod file leaves undeclared are taken from ion channel models."""

    def test_a_matching_entity_fills_the_missing_units(self):
        entity = _entity({"gbar": "S/cm2", "ik": "mA/cm2", "sh": "mV", "tau": "ms"})
        assert _database_units(_kmb(), [entity]) == {"sh": "mV", "tau": "ms"}

    def test_an_entity_whose_declared_units_differ_is_another_mechanism(self):
        other = _entity({"gbar": "mV", "sh": "ms", "tau": "ms"})
        assert _database_units(_kmb(), [other]) == {}

    def test_entities_that_disagree_on_a_missing_unit_give_none(self):
        a = _entity({"gbar": "S/cm2", "sh": "mV", "tau": "ms"})
        b = _entity({"gbar": "S/cm2", "sh": "mV", "tau": "s"})
        assert _database_units(_kmb(), [a, b]) == {"sh": "mV"}

    def test_entities_that_agree_give_one_unit(self):
        a = _entity({"sh": "mV"})
        b = _entity({"sh": "mV", "tau": None})
        assert _database_units(_kmb(), [a, b]) == {"sh": "mV"}

    def test_global_variables_are_filled_and_currents_are_not_looked_up(self):
        mechanism = ModMechanism(suffix="x", range_variables=["ik"], global_variables=["q10"])
        entity = _entity({"ik": "mA/cm2"}, {"q10": "1"})
        assert _database_units(mechanism, [entity]) == {"q10": "1"}

    def test_one_search_per_suffix_that_misses_a_unit(self):
        client = MagicMock()
        client.search_entity.return_value.all.return_value = [
            _entity({"gbar": "S/cm2", "sh": "mV", "tau": "ms"})
        ]
        kmb, kmb_again = _kmb(), _kmb()
        complete = ModMechanism(suffix="pas2", range_variables=["g"], units={"g": "S/cm2"})
        _fill_units_from_database(client, [kmb, kmb_again, complete])
        assert client.search_entity.call_args_list == [
            call(entity_type=IonChannelModel, query={"nmodl_suffix": "kmb"})
        ]
        assert kmb.units == kmb_again.units == {"gbar": "mho/cm2", "sh": "mV", "tau": "ms"}

    def test_nothing_missing_means_no_search(self):
        client = MagicMock()
        _fill_units_from_database(
            client, [ModMechanism(suffix="a", range_variables=["g"], units={"g": "S/cm2"})]
        )
        client.search_entity.assert_not_called()

    def test_a_failed_search_leaves_the_units_empty(self, caplog):
        client = MagicMock()
        client.search_entity.side_effect = EntitySDKError("HTTP error 503")
        kmb = _kmb()
        _fill_units_from_database(client, [kmb])
        assert kmb.units == {"gbar": "mho/cm2"}
        assert "Could not search ion channel models for kmb" in caplog.text

    def test_the_response_shows_the_unit_from_the_database(self, mock_db_client):
        """NaTg.mod of the tiny circuit declares no unit for slopem."""

        def search(*, entity_type, query, **_kwargs):
            result = MagicMock()
            result.all.return_value = (
                [_entity({"gNaTgbar": "S/cm2", "slopem": "mV"})]
                if entity_type is IonChannelModel and query == {"nmodl_suffix": "NaTg"}
                else []
            )
            return result

        mock_db_client.search_entity.side_effect = search
        result = get_circuit_manipulation_properties(
            db_client=mock_db_client, circuit_id=str(uuid4()), neuron_set=None
        )
        variables = result["MechanismVariablesByIonChannel"]["NaTg"].variables
        assert variables["slopem_NaTg"].units == "mV"
        assert not variables["slopeh_NaTg"].units

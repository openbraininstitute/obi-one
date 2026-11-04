"""Tests for circuit_metrics fetch_file integration with example circuit data."""

import shutil
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from entitysdk.types import FetchFileStrategy

from obi_one.scientific.library.circuit_constants import (
    CircuitStatsLevelOfDetail,
    EdgePopulationType,
    NodePopulationType,
)
from obi_one.scientific.library.circuit_metrics import (
    _build_edge_populations,
    _build_node_populations,
    get_circuit_metrics,
)

TINY_CIRCUIT_DIR = Path("examples/data/tiny_circuits/N_10__top_nodes_dim6")

_NODE_PROPS = {
    "pop_a": {
        "population_length": 10,
        "property_list": ["mtype"],
        "property_unique_values": {"mtype": ["L5_TPC"]},
        "property_value_counts": {"mtype": {"L5_TPC": 10}},
        "dynamics_param_names": ["gNa"],
    }
}

_EDGE_PROPS = {
    "edge_a": {
        "number_of_edges": 5,
        "source_name": "src",
        "target_name": "tgt",
        "property_list": ["delay"],
        "property_stats": {"delay": {"mean": 1.0}},
        "degrees": None,
    }
}


def _make_fetch_file_side_effect(circuit_dir: Path):
    """Return a side effect that copies files from circuit_dir to output_path."""

    def _fetch_file(*, output_path, asset_path, **_kwargs):
        src = circuit_dir / asset_path
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, output_path)

    return _fetch_file


@pytest.fixture
def db_client():
    client = MagicMock()
    asset = MagicMock()
    asset.is_directory = True
    asset.label.value = "sonata_circuit"
    asset.id = uuid4()
    entity = MagicMock()
    entity.assets = [asset]
    client.get_entity.return_value = entity
    client.fetch_file.side_effect = _make_fetch_file_side_effect(TINY_CIRCUIT_DIR)
    return client


def test_get_circuit_metrics_basic(db_client):
    """Test get_circuit_metrics with real circuit data at basic level of detail."""
    result = get_circuit_metrics(
        circuit_id=str(uuid4()),
        db_client=db_client,
        level_of_detail_nodes={"_ALL_": CircuitStatsLevelOfDetail.basic},
        level_of_detail_edges={"_ALL_": CircuitStatsLevelOfDetail.basic},
    )

    assert result.number_of_biophys_node_populations == 1
    assert result.number_of_virtual_node_populations == 2
    assert result.number_of_chemical_edge_populations == 3
    assert result.number_of_electrical_edge_populations == 0
    assert "S1nonbarrel_neurons" in result.names_of_biophys_node_populations
    assert len(result.names_of_nodesets) > 0

    # Verify fetch_file was called with the correct strategy
    for call in db_client.fetch_file.call_args_list:
        assert call.kwargs["strategy"] == FetchFileStrategy.link_or_download


class TestBuildNodePopulations:
    def test_missing_name_yields_none_slot(self):
        result = _build_node_populations(
            ["pop_a", "missing"],
            _NODE_PROPS,
            NodePopulationType.biophysical,
            include_dynamics_params=True,
        )
        assert result[0] is not None
        assert result[0].dynamics_param_names == ["gNa"]
        assert result[1] is None

    def test_dynamics_params_omitted_when_flag_false(self):
        result = _build_node_populations(
            ["pop_a"],
            _NODE_PROPS,
            NodePopulationType.virtual,
            include_dynamics_params=False,
        )
        assert result[0] is not None
        assert result[0].dynamics_param_names is None
        assert result[0].population_type == NodePopulationType.virtual


class TestBuildEdgePopulations:
    def test_missing_name_yields_none_slot(self):
        result = _build_edge_populations(
            ["edge_a", "missing"],
            _EDGE_PROPS,
            EdgePopulationType.chemical,
        )
        assert result[0] is not None
        assert result[0].number_of_edges == 5
        assert result[0].source_name == "src"
        assert result[1] is None

    def test_electrical_population_type(self):
        result = _build_edge_populations(
            ["edge_a"],
            _EDGE_PROPS,
            EdgePopulationType.electrical,
        )
        assert result[0] is not None
        assert result[0].population_type == EdgePopulationType.electrical

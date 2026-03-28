"""Tests for connectivity_metrics fetch_file integration with example circuit data."""

import shutil
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from entitysdk.types import FetchFileStrategy

from obi_one.scientific.library.connectivity_metrics import get_connectivity_metrics

TINY_CIRCUIT_DIR = Path("examples/data/tiny_circuits/N_10__top_nodes_dim6")


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


def test_get_connectivity_metrics(db_client):
    """Test get_connectivity_metrics with real circuit data."""
    result = get_connectivity_metrics(
        circuit_id=str(uuid4()),
        db_client=db_client,
        edge_population="S1nonbarrel_neurons__S1nonbarrel_neurons__chemical",
    )

    assert result.connection_probability is not None
    assert result.mean_number_of_synapses is not None

    # Verify fetch_file was called with the correct strategy
    for call in db_client.fetch_file.call_args_list:
        assert call.kwargs["strategy"] == FetchFileStrategy.link_or_download

import os
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import bluepysnap
import pandas as pd
import pytest

from obi_one.config import settings
from obi_one.scientific.from_id.em_cell_mesh_from_id import EMCellMeshFromID
from obi_one.scientific.tasks.point_neuron_circuit_from_em.task import (
    PointNeuronCircuitFromEMTask,
)

_TASK_MODULE = "obi_one.scientific.tasks.point_neuron_circuit_from_em.task"
_CAVE_KEY = settings.cave_client_config.microns_api_key


@pytest.fixture
def mock_db_client():
    return Mock()


def _mesh(pt_root_id, dataset_id, cave_version=3):
    """A mock EMCellMeshFromID whose resolution methods return fixed provenance."""
    mesh = Mock()
    mesh.pt_root_id.return_value = pt_root_id
    mesh.cave_version.return_value = cave_version
    mesh.source_dataset.return_value = SimpleNamespace(id=dataset_id, name="ds")
    return mesh


def _make_task(meshes):
    config = Mock()
    config.initialize.cell_meshes.elements = tuple(meshes)
    return PointNeuronCircuitFromEMTask.model_construct(config=config)


def _synapses_df(pre_ids, post_id):
    return pd.DataFrame(
        {
            "pre_pt_root_id": pre_ids,
            "post_pt_root_id": [post_id] * len(pre_ids),
        }
    )


class TestEMCellMeshFromID:
    def test_resolves_provenance_and_caches(self):
        mesh = EMCellMeshFromID(id_str="abc")
        db = Mock()
        ds_id = uuid4()
        mesh_entity = SimpleNamespace(
            dense_reconstruction_cell_id=42,
            release_version=7,
            em_dense_reconstruction_dataset=SimpleNamespace(id=ds_id),
        )
        dataset_entity = SimpleNamespace(id=ds_id, name="ds")

        def get_entity(entity_id, entity_type):  # noqa: ARG001
            return mesh_entity if str(entity_id) == "abc" else dataset_entity

        db.get_entity.side_effect = get_entity

        assert mesh.pt_root_id(db) == 42
        assert mesh.cave_version(db) == 7
        assert mesh.source_dataset(db).id == ds_id

        # The mesh entity and the source dataset are both cached: repeated calls do not re-fetch.
        mesh.source_dataset(db)
        mesh.pt_root_id(db)
        assert db.get_entity.call_count == 2


class TestPointNeuronCircuitFromEMTask:
    def test_execute_requires_db_client(self):
        task = _make_task([_mesh(111, uuid4())])
        with pytest.raises(ValueError, match="db_client"):
            task.execute(db_client=None)

    def test_execute_rejects_mixed_datasets(self, mock_db_client):
        # Two meshes from different EM datasets.
        task = _make_task([_mesh(111, uuid4()), _mesh(222, uuid4())])
        with pytest.raises(ValueError, match="same EM dense reconstruction"):
            task.execute(db_client=mock_db_client)

    def test_execute_rejects_duplicate_pt_root_ids(self, mock_db_client):
        ds_id = uuid4()
        task = _make_task([_mesh(111, ds_id), _mesh(111, ds_id)])
        with pytest.raises(ValueError, match="Duplicate EM cell mesh"):
            task.execute(db_client=mock_db_client)

    def test_execute_resolves_connectivity_and_writes_circuit(self, mock_db_client, tmp_path):
        ds_id = uuid4()
        task = _make_task([_mesh(111, ds_id), _mesh(222, ds_id)])
        task.config.coordinate_output_root = tmp_path

        # Neuron 111: 2 internal synapses from 222, 1 external from 999.
        # Neuron 222: 1 internal synapse from 111, 1 external from 888.
        syn_map = {
            111: _synapses_df([222, 222, 999], 111),
            222: _synapses_df([111, 888], 222),
        }

        def fake_synapse_info_df(post_pt_root_id, cave_version, col_location=None, db_client=None):  # noqa: ARG001
            return syn_map[post_pt_root_id], "notice"

        em_dataset = Mock()
        em_dataset.synapse_info_df.side_effect = fake_synapse_info_df

        with (
            patch.dict(os.environ, {_CAVE_KEY: "fake-key"}),
            patch(f"{_TASK_MODULE}.EMDataSetFromID", return_value=em_dataset),
            patch(
                f"{_TASK_MODULE}.register_point_neuron_circuit", return_value="circuit-id"
            ) as mock_register,
        ):
            task.execute(db_client=mock_db_client)

        # Internal connectivity matrix (rows = pre, cols = post).
        conn = task.internal_connectivity
        assert conn.loc[222, 111] == 2
        assert conn.loc[111, 222] == 1
        assert conn.loc[111, 111] == 0
        assert conn.loc[222, 222] == 0

        # Per-neuron afferent summary.
        summary = task.neuron_summary
        assert summary.loc[111, "total_afferent_synapses"] == 3
        assert summary.loc[111, "internal_afferent_synapses"] == 2
        assert summary.loc[111, "external_afferent_synapses"] == 1
        assert summary.loc[111, "external_presynaptic_partners"] == 1
        assert summary.loc[222, "total_afferent_synapses"] == 2
        assert summary.loc[222, "internal_afferent_synapses"] == 1
        assert summary.loc[222, "external_presynaptic_partners"] == 1

        # The EM dataset is built with the shared source dataset id and queried per neuron.
        assert em_dataset.synapse_info_df.call_count == 2

        # A Brian2 SONATA circuit was written and loads with bluepysnap.
        assert task.circuit_config_path == tmp_path / "circuit_config.json"
        assert (tmp_path / "nodes.h5").exists()
        assert (tmp_path / "edges.h5").exists()
        assert (tmp_path / "models" / "point_neuron.json").exists()

        circuit = bluepysnap.Circuit(str(task.circuit_config_path))
        assert circuit.nodes["point_neurons"].size == 2
        assert circuit.nodes["virtual_afferent_neurons"].size == 2

        # The written circuit is registered (registration itself is mocked here).
        mock_register.assert_called_once()
        assert mock_register.call_args.kwargs["circuit_path"] == task.circuit_config_path
        assert mock_register.call_args.kwargs["point_pt_root_ids"] == [111, 222]
        assert mock_register.call_args.kwargs["virtual_count"] == 2
        assert task.registered_circuit_id == "circuit-id"

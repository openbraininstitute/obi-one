import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.named_tuple_from_id import EMSynapseMappingInputNamedTuple
from obi_one.scientific.tasks.em_synapse_mapping.task import (
    EMSynapseMappingTask,
)


@pytest.fixture
def mock_db_client():
    return Mock()


def _resolved_neuron(pt_root_id, name, *, use_me_model=False):
    dataset_id = uuid4()
    return SimpleNamespace(
        pt_root_id=pt_root_id,
        morph_entity=SimpleNamespace(id=uuid4(), name=name),
        morph_from_id=Mock(),
        spiny_morph=Mock(),
        smooth_morph=Mock(),
        source_mesh_entity=Mock(),
        source_dataset=SimpleNamespace(id=dataset_id, name="ds"),
        cave_version=3,
        use_me_model=use_me_model,
        phys_node_props={},
        fn_morph_h5=Path(f"morphologies/{name}.h5"),
        fn_morph_swc=Path(f"morphologies/morphology/{name}.swc"),
    )


def _make_resolved_pair():
    """Two resolved neurons sharing the same dataset id."""
    ds_id = uuid4()
    rn1 = _resolved_neuron(111, "neuron_A")
    rn2 = _resolved_neuron(222, "neuron_B")
    rn1.source_dataset = SimpleNamespace(id=ds_id, name="ds")
    rn2.source_dataset = SimpleNamespace(id=ds_id, name="ds")
    return [rn1, rn2]


def _synapses_df(pre_ids, post_id):
    return pd.DataFrame(
        {
            "pre_pt_root_id": pre_ids,
            "post_pt_root_id": [post_id] * len(pre_ids),
        }
    )


def _mapped_df(n):
    return pd.DataFrame(
        {
            "distance": np.random.default_rng(0).random(n),
            "competing_distance": np.random.default_rng(1).random(n),
        }
    )


def _make_task(tmp_path):
    config = Mock()
    config.coordinate_output_root = tmp_path / "out"
    config.initialize.neurons = EMSynapseMappingInputNamedTuple(
        name="test",
        elements=(
            CellMorphologyFromID(id_str="test1"),
            CellMorphologyFromID(id_str="test2"),
        ),
    )
    config.initialize.biophysical_node_population = "bio"
    config.initialize.virtual_node_population = "virt"
    config.initialize.physical_edge_population_name = "phys"
    config.initialize.virtual_edge_population_name = "virt_edges"
    return EMSynapseMappingTask.model_construct(config=config)


_TASK_MODULE = "obi_one.scientific.tasks.em_synapse_mapping.task"


class TestEMSynapseMappingTask:
    def test_execute_requires_db_client(self, tmp_path):
        task = _make_task(tmp_path)
        with pytest.raises(ValueError, match="db_client"):
            task.execute(db_client=None)

    def test_execute_rejects_mixed_datasets(self, tmp_path, mock_db_client):
        task = _make_task(tmp_path)
        rn1 = _resolved_neuron(111, "A")
        rn2 = _resolved_neuron(222, "B")
        # Different dataset ids

        with (
            patch.object(EMSynapseMappingTask, "_get_execution_activity", return_value=None),
            patch(
                f"{_TASK_MODULE}.resolve_neuron",
                side_effect=[rn1, rn2],
            ),
            pytest.raises(ValueError, match="same EM dense reconstruction"),
        ):
            task.execute(db_client=mock_db_client)

    def test_execute_happy_path(self, tmp_path, mock_db_client):
        task = _make_task(tmp_path)
        resolved = _make_resolved_pair()

        # Neuron 0 (pt_root_id=111): 2 internal synapses from 222, 1 external from 999
        syns_0 = _synapses_df([222, 222, 999], 111)
        mapped_0 = _mapped_df(3)

        # Neuron 1 (pt_root_id=222): 1 internal from 111, 1 external from 888
        syns_1 = _synapses_df([111, 888], 222)
        mapped_1 = _mapped_df(2)

        coll_bio = SimpleNamespace(properties={})
        coll_virt = SimpleNamespace(properties={})

        call_count = {"n": 0}

        def fake_synapses_and_nodes(*_args, **_kwargs):
            idx = call_count["n"]
            call_count["n"] += 1
            if idx == 0:
                return syns_0, Mock(), Mock(), ["notice-0"]
            return syns_1, Mock(), Mock(), ["notice-1"]

        def fake_assemble(*_args, **_kwargs):
            mapping = _args[4] if len(_args) > 4 else _kwargs.get("mapping")
            if len(mapping) == 2:
                return coll_bio, []
            return coll_virt, []

        with (
            patch.dict(os.environ, {"CAVECLIENT_MICRONS_API_KEY": "fake-key"}),
            patch.object(EMSynapseMappingTask, "_get_execution_activity", return_value=None),
            patch(f"{_TASK_MODULE}.resolve_neuron", side_effect=resolved),
            patch(f"{_TASK_MODULE}.EMDataSetFromID") as mock_em_ds,
            patch(f"{_TASK_MODULE}.merge_spiny_morphologies"),
            patch(
                f"{_TASK_MODULE}.synapses_and_nodes_dataframes_from_EM",
                side_effect=fake_synapses_and_nodes,
            ),
            patch(
                f"{_TASK_MODULE}.map_afferents_to_spiny_morphology",
                side_effect=[(mapped_0, 0.5), (mapped_1, 0.5)],
            ),
            patch(
                f"{_TASK_MODULE}.plot_mapping_stats",
                return_value=Mock(savefig=Mock()),
            ),
            patch(f"{_TASK_MODULE}.plt"),
            patch(f"{_TASK_MODULE}.default_node_spec_for", return_value={}),
            patch(
                f"{_TASK_MODULE}.assemble_collection_from_specs",
                side_effect=fake_assemble,
            ),
            patch(f"{_TASK_MODULE}.write_nodes"),
            patch(f"{_TASK_MODULE}.write_edges"),
            patch(f"{_TASK_MODULE}.sonata_config_for", return_value={"version": 2.3}),
            patch(
                f"{_TASK_MODULE}.compress_output",
                return_value=str(tmp_path / "out" / "sonata.tar.gz"),
            ),
            patch(
                f"{_TASK_MODULE}.register_output",
                return_value="circuit-id",
            ) as mock_register,
            patch.object(EMSynapseMappingTask, "_update_execution_activity") as mock_update,
        ):
            mock_em_ds.return_value = Mock()
            task.execute(db_client=mock_db_client)

        mock_register.assert_called_once()
        mock_update.assert_called_once()

    def test_execute_with_me_model_props(self, tmp_path, mock_db_client):
        """Test that ME model properties are correctly merged into biophysical nodes."""
        task = _make_task(tmp_path)
        resolved = _make_resolved_pair()
        # Give the first neuron ME model properties
        resolved[0].use_me_model = True
        resolved[0].phys_node_props = {
            "model_template": np.array(["hoc:model"]),
            "threshold_current": np.array([0.5], dtype=np.float32),
        }

        syns = _synapses_df([999], 111)
        mapped = _mapped_df(1)

        bio_props = {}
        coll_bio = SimpleNamespace(properties=bio_props)

        def fake_synapses(*_a, **_k):
            return syns, Mock(), Mock(), []

        def fake_assemble(*_a, **_k):
            return coll_bio, []

        with (
            patch.dict(os.environ, {"CAVECLIENT_MICRONS_API_KEY": "fake-key"}),
            patch.object(EMSynapseMappingTask, "_get_execution_activity", return_value=None),
            patch(f"{_TASK_MODULE}.resolve_neuron", side_effect=resolved),
            patch(f"{_TASK_MODULE}.EMDataSetFromID"),
            patch(f"{_TASK_MODULE}.merge_spiny_morphologies"),
            patch(
                f"{_TASK_MODULE}.synapses_and_nodes_dataframes_from_EM",
                side_effect=fake_synapses,
            ),
            patch(
                f"{_TASK_MODULE}.map_afferents_to_spiny_morphology",
                return_value=(mapped, 0.5),
            ),
            patch(
                f"{_TASK_MODULE}.plot_mapping_stats",
                return_value=Mock(savefig=Mock()),
            ),
            patch(f"{_TASK_MODULE}.plt"),
            patch(f"{_TASK_MODULE}.default_node_spec_for", return_value={}),
            patch(
                f"{_TASK_MODULE}.assemble_collection_from_specs",
                side_effect=fake_assemble,
            ),
            patch(f"{_TASK_MODULE}.write_nodes"),
            patch(f"{_TASK_MODULE}.write_edges"),
            patch(f"{_TASK_MODULE}.sonata_config_for", return_value={}),
            patch(
                f"{_TASK_MODULE}.compress_output",
                return_value=str(tmp_path / "out" / "sonata.tar.gz"),
            ),
            patch(f"{_TASK_MODULE}.register_output", return_value="cid"),
            patch.object(EMSynapseMappingTask, "_update_execution_activity"),
        ):
            task.execute(db_client=mock_db_client)

        assert "model_template" in bio_props
        assert "threshold_current" in bio_props

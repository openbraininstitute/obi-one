from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pandas as pd
import pytest

from obi_one.scientific.tasks.em_synapse_mapping.task import EMSynapseMappingTask


@pytest.fixture
def mock_db_client():
    return Mock()


@pytest.fixture
def resolved_neuron():
    return SimpleNamespace(
        pt_root_id=42,
        morph_entity=SimpleNamespace(id=uuid4(), name="morph_A"),
        morph_from_id=Mock(),
        spiny_morph=SimpleNamespace(morphology=SimpleNamespace(name="morph_A")),
        smooth_morph=Mock(),
        source_mesh_entity=Mock(),
        source_dataset=SimpleNamespace(id=uuid4(), name="ds"),
        cave_version=3,
        use_me_model=False,
        phys_node_props={},
        fn_morph_h5=Path("morphologies/morph_A.h5"),
        fn_morph_swc=Path("morphologies/morphology/morph_A.swc"),
    )


@pytest.fixture
def synapses_df():
    return pd.DataFrame({"pre_pt_root_id": [100, 100, 200], "post_pt_root_id": [42, 42, 42]})


@pytest.fixture
def mapped_synapses_df():
    return pd.DataFrame({"distance": [0.1, 0.2, 0.3], "competing_distance": [0.5, 0.6, 0.7]})


def _make_task(tmp_path):
    config = Mock()
    config.coordinate_output_root = tmp_path / "out"
    config.initialize.spiny_neuron = Mock()
    config.initialize.edge_population_name = "afferent_synapses"
    config.initialize.node_population_pre = "pre_pop"
    config.initialize.node_population_post = "post_pop"
    return EMSynapseMappingTask.model_construct(config=config)


class TestEMSynapseMappingTask:
    def test_execute_requires_db_client(self, tmp_path):
        task = _make_task(tmp_path)
        with pytest.raises(ValueError, match="db_client"):
            task.execute(db_client=None)

    def test_execute_happy_path(
        self, tmp_path, mock_db_client, resolved_neuron, synapses_df, mapped_synapses_df
    ):
        task = _make_task(tmp_path)

        coll_pre = SimpleNamespace(properties={})
        coll_post = SimpleNamespace(properties={})

        with (
            patch.object(
                EMSynapseMappingTask,
                "_get_execution_activity",
                return_value=None,
            ),
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.task.resolve_neuron",
                return_value=resolved_neuron,
            ),
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.task.EMDataSetFromID",
            ) as mock_em_ds,
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.task.synapses_and_nodes_dataframes_from_EM",
                return_value=(synapses_df, coll_pre, coll_post, ["notice"]),
            ),
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.task.map_afferents_to_spiny_morphology",
                return_value=(mapped_synapses_df, 0.5),
            ),
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.task.plot_mapping_stats",
                return_value=Mock(savefig=Mock()),
            ),
            patch("obi_one.scientific.tasks.em_synapse_mapping.task.write_edges"),
            patch("obi_one.scientific.tasks.em_synapse_mapping.task.write_nodes"),
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.task.sonata_config_for",
                return_value={"version": 2.3},
            ),
            patch("obi_one.scientific.tasks.em_synapse_mapping.task.write_json"),
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.task.compress_output",
                return_value="/fake/path.tar.gz",
            ),
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.task.register_output_single",
                return_value="circuit-id-123",
            ) as mock_register,
            patch.object(EMSynapseMappingTask, "_update_execution_activity"),
        ):
            mock_em_ds.return_value.entity.return_value = SimpleNamespace(license="lic")
            task.execute(db_client=mock_db_client)

        mock_register.assert_called_once()

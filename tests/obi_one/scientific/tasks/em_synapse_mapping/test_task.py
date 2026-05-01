import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pandas as pd
import pytest

from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.named_tuple_from_id import EMSynapseMappingInputNamedTuple
from obi_one.scientific.tasks.em_synapse_mapping.task import EMSynapseMappingTask

_TASK_MODULE = "obi_one.scientific.tasks.em_synapse_mapping.task"


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
    """Build a single-neuron task using the unified config shape."""
    config = Mock()
    config.coordinate_output_root = tmp_path / "out"
    config.initialize.neurons = EMSynapseMappingInputNamedTuple(
        name="test", elements=(CellMorphologyFromID(id_str="test"),)
    )
    config.initialize.biophysical_node_population = "post_pop"
    config.initialize.virtual_node_population = "pre_pop"
    config.initialize.physical_edge_population_name = "physical_connections"
    config.initialize.virtual_edge_population_name = "afferent_synapses"
    return EMSynapseMappingTask.model_construct(config=config)


class TestEMSynapseMappingTask:
    def test_execute_requires_db_client(self, tmp_path):
        task = _make_task(tmp_path)
        with pytest.raises(ValueError, match="db_client"):
            task.execute(db_client=None)

    def test_execute_single_neuron_happy_path(
        self, tmp_path, mock_db_client, resolved_neuron, synapses_df, mapped_synapses_df
    ):
        task = _make_task(tmp_path)

        coll_bio = SimpleNamespace(properties={})
        coll_virt = SimpleNamespace(properties={})

        def fake_assemble(*_args, **_kwargs):
            mapping = _args[4] if len(_args) > 4 else _kwargs.get("mapping")
            if len(mapping) == 1:
                return coll_bio, []
            return coll_virt, []

        with (
            patch.dict(os.environ, {"CAVECLIENT_MICRONS_API_KEY": "fake-key"}),
            patch.object(
                EMSynapseMappingTask,
                "_get_execution_activity",
                return_value=None,
            ),
            patch(
                f"{_TASK_MODULE}.resolve_neuron",
                return_value=resolved_neuron,
            ),
            patch(f"{_TASK_MODULE}.EMDataSetFromID") as mock_em_ds,
            patch(
                f"{_TASK_MODULE}.synapses_and_nodes_dataframes_from_EM",
                return_value=(synapses_df, Mock(), Mock(), ["notice"]),
            ),
            patch(
                f"{_TASK_MODULE}.map_afferents_to_spiny_morphology",
                return_value=(mapped_synapses_df, 0.5),
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
            patch(
                f"{_TASK_MODULE}.sonata_config_for",
                return_value={"version": 2.3},
            ),
            patch(
                f"{_TASK_MODULE}.compress_output",
                return_value="/fake/path.tar.gz",
            ),
            patch(
                f"{_TASK_MODULE}.register_output",
                return_value="circuit-id-123",
            ) as mock_register,
            patch.object(EMSynapseMappingTask, "_update_execution_activity"),
        ):
            mock_em_ds.return_value = Mock()
            task.execute(db_client=mock_db_client)

        mock_register.assert_called_once()

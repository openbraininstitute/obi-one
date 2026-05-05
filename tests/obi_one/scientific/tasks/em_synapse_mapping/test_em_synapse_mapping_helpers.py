from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pandas as pd
import pytest
from entitysdk._server_schemas import PublicationType

from obi_one.scientific.tasks.em_synapse_mapping.dataframes_from_em import (
    synapses_and_nodes_dataframes_from_EM,
)
from obi_one.scientific.tasks.em_synapse_mapping.plot import plot_mapping_stats
from obi_one.scientific.tasks.em_synapse_mapping.publication_links import (
    assemble_publication_links,
)
from obi_one.scientific.tasks.em_synapse_mapping.register import register_output
from obi_one.scientific.tasks.em_synapse_mapping.resolve_neuron import resolve_provenance
from obi_one.scientific.tasks.em_synapse_mapping.util import compress_output


@pytest.fixture
def mock_db_client():
    return Mock()


@pytest.fixture
def synapses_df():
    return pd.DataFrame(
        {
            "pre_pt_root_id": [1, 1, 2],
            "post_pt_root_id": [7, 7, 9],
        }
    )


@pytest.fixture
def source_dataset():
    return SimpleNamespace(
        name="dataset",
        subject="subject",
        brain_region="region",
        experiment_date="2024-01-01",
    )


@pytest.fixture
def em_dataset():
    return SimpleNamespace(id=uuid4(), license="license")


def test_compress_output(tmp_path):
    out_root = tmp_path / "out"
    out_root.mkdir()
    test_files = [str(out_root / "a.h5"), str(out_root / "b.h5")]

    with (
        patch(
            "obi_one.scientific.tasks.em_synapse_mapping.util.subprocess.check_output",
            return_value=b"tar-bytes",
        ) as mock_check_output,
        patch(
            "obi_one.scientific.tasks.em_synapse_mapping.util.subprocess.check_call"
        ) as mock_check_call,
    ):
        compressed_path = compress_output(out_root, test_files)

    assert compressed_path == str(out_root / "sonata.tar.gz")
    assert (out_root / "sonata.tar").read_bytes() == b"tar-bytes"
    mock_check_output.assert_called_once_with(["tar", "-cf", "-", *test_files])
    mock_check_call.assert_called_once_with(["gzip", "-1", "-f", str(out_root / "sonata.tar")])


def test_assemble_publication_links_filters_application(mock_db_client):
    publication_keep = SimpleNamespace(id=uuid4())
    publication_ignore = SimpleNamespace(id=uuid4())
    src_links = [
        SimpleNamespace(
            publication=publication_keep, publication_type=PublicationType.component_source
        ),
        SimpleNamespace(
            publication=publication_ignore, publication_type=PublicationType.application
        ),
    ]
    mock_db_client.search_entity.return_value.all.return_value = src_links

    links = assemble_publication_links(mock_db_client, SimpleNamespace(id=uuid4()), [])

    assert links == [publication_keep]
    mock_db_client.search_entity.assert_called_once()


def test_resolve_provenance(mock_db_client):
    dataset_id = uuid4()
    source_mesh = SimpleNamespace(
        dense_reconstruction_cell_id=1234,
        em_dense_reconstruction_dataset=SimpleNamespace(id=dataset_id),
    )
    resolved_source_dataset = SimpleNamespace(id=dataset_id, name="dataset")
    morph_from_id = Mock()
    morph_from_id.source_mesh_entity.return_value = source_mesh
    mock_db_client.get_entity.return_value = resolved_source_dataset

    pt_root_id, source_mesh_entity, resolved_dataset = resolve_provenance(
        mock_db_client, morph_from_id
    )

    assert pt_root_id == 1234
    assert source_mesh_entity is source_mesh
    assert resolved_dataset is resolved_source_dataset
    mock_db_client.get_entity.assert_called_once()


def test_synapses_and_nodes_dataframes_from_em(mock_db_client, synapses_df):
    em_dataset = Mock()
    em_dataset.synapse_info_df.return_value = (synapses_df, "syn-notice")
    coll_pre = SimpleNamespace(name="pre")
    coll_post = SimpleNamespace(name="post")

    with (
        patch(
            "obi_one.scientific.tasks.em_synapse_mapping.dataframes_from_em.default_node_spec_for",
            return_value="node-spec",
        ),
        patch(
            "obi_one.scientific.tasks.em_synapse_mapping.dataframes_from_em.assemble_collection_from_specs",
            side_effect=[(coll_pre, ["n1", "n2"]), (coll_post, ["ignored"])],
        ) as mock_assemble,
    ):
        syns, pre, post, notices = synapses_and_nodes_dataframes_from_EM(
            em_dataset=em_dataset, pt_root_id=123, db_client=mock_db_client, cave_version=7
        )

    assert syns.equals(synapses_df)
    assert pre is coll_pre
    assert post is coll_post
    assert notices == ["syn-notice", "n1", "n2"]
    assert mock_assemble.call_count == 2


def test_plot_mapping_stats():
    mapped_synapses_df = pd.DataFrame(
        {
            "distance": [-1.0, 0.5, 2.2],
            "competing_distance": [0.2, 1.1, 2.8],
        }
    )

    fig = plot_mapping_stats(mapped_synapses_df, mesh_res=0.5)

    assert len(fig.axes) == 1
    assert fig.axes[0].get_ylabel() == "Synapse count"


def test_register_output(tmp_path, mock_db_client, source_dataset, em_dataset):
    existing_circuit = SimpleNamespace(id=uuid4())
    mock_db_client.register_entity.side_effect = [existing_circuit, "link-1", "link-2"]

    file_paths = {"a.txt": str(tmp_path / "a.txt")}
    compressed_path = tmp_path / "sonata.tar.gz"

    resolved_neuron = SimpleNamespace(
        pt_root_id=42,
        use_me_model=False,
        phys_node_props={},
    )

    with (
        patch(
            "obi_one.scientific.tasks.em_synapse_mapping.register.assemble_publication_links",
            return_value=[SimpleNamespace(id=1), SimpleNamespace(id=2)],
        ) as mock_links,
        patch(
            "obi_one.scientific.tasks.em_synapse_mapping.register.Circuit",
            return_value=SimpleNamespace(name="fake-circuit"),
        ),
        patch(
            "obi_one.scientific.tasks.em_synapse_mapping.register.ScientificArtifactPublicationLink",
            return_value=SimpleNamespace(id=uuid4()),
        ),
    ):
        em_dataset_from_id = Mock()
        em_dataset_from_id.entity.return_value = em_dataset
        circuit_id = register_output(
            db_client=mock_db_client,
            resolved_neurons=[resolved_neuron],
            source_dataset=source_dataset,
            em_dataset=em_dataset_from_id,
            all_notices=["notice"],
            total_synapses=3,
            total_connections=2,
            total_internal=0,
            total_external=3,
            file_paths=file_paths,
            compressed_path=compressed_path,
        )

    assert circuit_id == str(existing_circuit.id)
    mock_db_client.upload_directory.assert_called_once()
    mock_db_client.upload_file.assert_called_once()
    mock_links.assert_called_once_with(mock_db_client, em_dataset, ["notice"])
    assert mock_db_client.register_entity.call_count == 3

"""Unit tests for shared circuit endpoint helpers."""

from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

from entitysdk.types import AssetLabel, CircuitScale

from app.endpoints.circuit_helpers import (
    compute_circuit_metadata,
    generate_and_register_visualization_assets,
    upload_sonata_circuit,
)

from tests.utils import CIRCUIT_DIR


class TestComputeCircuitMetadata:
    def test_loads_tiny_circuit_counts(self):
        config_path = CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"
        (
            circuit,
            scale,
            number_neurons,
            number_synapses,
            number_connections,
            has_morphologies,
            has_point_neurons,
            has_electrical_cell_models,
            has_spines,
        ) = compute_circuit_metadata("tiny", config_path)

        assert circuit.name == "tiny"
        assert scale == CircuitScale.small
        assert number_neurons == 10
        assert number_synapses > 0
        assert number_connections is None or number_connections >= 0
        assert has_morphologies is True
        assert has_point_neurons is False
        assert has_electrical_cell_models is True
        assert isinstance(has_spines, bool)


class TestUploadSonataCircuit:
    def test_uploads_all_files_under_circuit_dir(self, tmp_path: Path):
        circuit_dir = tmp_path / "circuit"
        (circuit_dir / "nested").mkdir(parents=True)
        (circuit_dir / "circuit_config.json").write_text("{}", encoding="utf-8")
        (circuit_dir / "nested" / "nodes.h5").write_bytes(b"h5")

        mock_client = MagicMock()
        registered = MagicMock()
        registered.id = uuid4()

        upload_sonata_circuit(mock_client, registered, circuit_dir)

        mock_client.upload_directory.assert_called_once()
        kwargs = mock_client.upload_directory.call_args.kwargs
        assert kwargs["entity_id"] == registered.id
        assert kwargs["name"] == "sonata_circuit"
        assert kwargs["label"] == AssetLabel.sonata_circuit
        paths = kwargs["paths"]
        assert Path("circuit_config.json") in paths
        assert Path("nested/nodes.h5") in paths
        assert paths[Path("circuit_config.json")] == circuit_dir / "circuit_config.json"


class TestGenerateAndRegisterVisualizationAssets:
    def test_skips_when_no_edge_populations(self, tmp_path: Path):
        circuit = MagicMock()
        circuit.sonata_circuit.edges.population_names = []
        circuit.default_edge_population_name = "unused"

        with (
            patch(
                "app.endpoints.circuit_helpers.generate_connectivity_matrix_asset"
            ) as mock_matrix,
            patch("app.endpoints.circuit_helpers.generate_connectivity_plot_assets") as mock_plots,
            patch("app.endpoints.circuit_helpers.generate_overview_image_asset") as mock_overview,
            patch(
                "app.endpoints.circuit_helpers.generate_sim_designer_image_asset"
            ) as mock_sim_designer,
        ):
            generate_and_register_visualization_assets(
                circuit=circuit,
                config_path=tmp_path / "circuit_config.json",
                output_root=tmp_path,
                db_client=MagicMock(),
                registered=MagicMock(),
            )

        mock_matrix.assert_not_called()
        mock_plots.assert_not_called()
        mock_overview.assert_not_called()
        mock_sim_designer.assert_not_called()

    def test_generates_matrix_plots_and_images(self, tmp_path: Path):
        circuit = MagicMock()
        circuit.sonata_circuit.edges.population_names = ["edges"]
        circuit.default_edge_population_name = "edges"

        config_path = tmp_path / "circuit_config.json"
        config_path.write_text("{}", encoding="utf-8")
        db_client = MagicMock()
        registered = MagicMock()

        with (
            patch(
                "app.endpoints.circuit_helpers.generate_connectivity_matrix_asset",
                return_value=(tmp_path / "matrix", "matrix.json", "edges"),
            ) as mock_matrix,
            patch("app.endpoints.circuit_helpers.generate_connectivity_plot_assets") as mock_plots,
            patch("app.endpoints.circuit_helpers.generate_overview_image_asset") as mock_overview,
            patch(
                "app.endpoints.circuit_helpers.generate_sim_designer_image_asset"
            ) as mock_sim_designer,
        ):
            generate_and_register_visualization_assets(
                circuit=circuit,
                config_path=config_path,
                output_root=tmp_path,
                db_client=db_client,
                registered=registered,
            )

        mock_matrix.assert_called_once_with(
            circuit_path=config_path,
            output_dir=tmp_path / "__CONN_MATRIX__",
            edge_population="edges",
        )
        mock_plots.assert_called_once_with(
            matrix_config="matrix.json",
            edge_population="edges",
            output_dir=tmp_path / "__BASIC_PLOTS__",
            client=db_client,
            circuit_entity=registered,
        )
        mock_overview.assert_called_once_with(
            plot_dir=tmp_path / "__BASIC_PLOTS__",
            output_dir=tmp_path / "__CIRCUIT_VIZ__",
            client=db_client,
            circuit_entity=registered,
        )
        mock_sim_designer.assert_called_once_with(
            plot_dir=tmp_path / "__BASIC_PLOTS__",
            output_dir=tmp_path / "__CIRCUIT_VIZ__",
            client=db_client,
            circuit_entity=registered,
        )

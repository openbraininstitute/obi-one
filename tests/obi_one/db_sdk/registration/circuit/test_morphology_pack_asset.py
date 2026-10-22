import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from entitysdk import MultipartUploadTransferConfig
from entitysdk.types import AssetLabel, AssetStatus

from obi_one.db_sdk.registration.circuit import generate
from obi_one.db_sdk.registration.circuit.assets import add_morphology_pack_asset
from obi_one.db_sdk.registration.circuit.generate import (
    generate_additional_circuit_assets,
    generate_morphology_pack_asset,
    missing_assets,
)
from obi_one.scientific.library.morphology_pack.build import NoPackError

from tests.utils import CIRCUIT_DIR

CONTAINER_CIRCUIT = CIRCUIT_DIR / "N_10__top_nodes_dim6"
STEPS = (
    "generate_compressed_circuit_asset",
    "generate_connectivity_matrix_asset",
    "generate_overview_image_asset",
    "generate_sim_designer_image_asset",
)


def circuit_with(*labels: str, scale: str = "small") -> MagicMock:
    circuit = MagicMock()
    circuit.id = "circuit-1"
    circuit.name = "my_circuit"
    circuit.scale = scale
    circuit.assets = [MagicMock(label=label) for label in labels]
    return circuit


@pytest.fixture
def config(tmp_path) -> Path:
    circuit_dir = tmp_path / "my_circuit"
    circuit_dir.mkdir()
    path = circuit_dir / "circuit_config.json"
    path.write_text("{}")
    return path


@pytest.fixture
def other_steps():
    """The other steps, standing in; the matrices' gives what the plots need."""
    with (
        patch.object(generate, "generate_compressed_circuit_asset") as compressed,
        patch.object(
            generate,
            "generate_connectivity_matrix_asset",
            return_value=(MagicMock(), MagicMock(), "edges"),
        ) as matrices,
        patch.object(generate, "generate_connectivity_plot_assets"),
        patch.object(generate, "generate_overview_image_asset") as overview,
        patch.object(generate, "generate_sim_designer_image_asset") as sim_designer,
    ):
        yield [compressed, matrices, overview, sim_designer]


@pytest.fixture
def pack_step():
    with patch.object(generate, "generate_morphology_pack_asset") as step:
        yield step


class TestMissingAssets:
    def test_every_one_on_a_bare_circuit(self):
        assert missing_assets(circuit_with()) == {
            AssetLabel.compressed_sonata_circuit,
            AssetLabel.circuit_connectivity_matrices,
            AssetLabel.circuit_morphology_pack,
        }

    def test_the_pack_alone(self):
        circuit = circuit_with("compressed_sonata_circuit", "circuit_connectivity_matrices")
        assert missing_assets(circuit) == {AssetLabel.circuit_morphology_pack}

    def test_a_pack_still_uploading(self):
        circuit = circuit_with("compressed_sonata_circuit", "circuit_connectivity_matrices")
        circuit.assets.append(
            MagicMock(label="circuit_morphology_pack", status=AssetStatus.uploading)
        )
        assert missing_assets(circuit) == {AssetLabel.circuit_morphology_pack}

    def test_no_pack_expected_of_a_single_neuron(self):
        circuit = circuit_with(
            "compressed_sonata_circuit", "circuit_connectivity_matrices", scale="single"
        )
        assert missing_assets(circuit) == set()

    def test_images_are_not_expected(self):
        circuit = circuit_with(
            "compressed_sonata_circuit",
            "circuit_connectivity_matrices",
            "circuit_morphology_pack",
        )
        assert missing_assets(circuit) == set()


@pytest.mark.usefixtures("other_steps")
class TestStep:
    def test_built_last_when_missing(self, config, other_steps, pack_step):
        order = MagicMock()
        for step, mock in zip(STEPS, other_steps, strict=True):
            order.attach_mock(mock, step)
        order.attach_mock(pack_step, "pack")
        generate_additional_circuit_assets(
            circuit_path=config, edge_population="edges", circuit_entity=circuit_with()
        )
        assert [name for name, _, _ in order.mock_calls][-1] == "pack"
        assert pack_step.call_args.kwargs["output_dir"] == (
            config.parents[1] / "my_circuit__MORPHOLOGY_PACK__"
        )

    def test_skipped_when_present(self, config, pack_step):
        circuit = circuit_with("circuit_morphology_pack")
        generate_additional_circuit_assets(circuit_path=config, circuit_entity=circuit)
        pack_step.assert_not_called()

    def test_built_again_with_force(self, config, pack_step):
        circuit = circuit_with("circuit_morphology_pack")
        generate_additional_circuit_assets(circuit_path=config, circuit_entity=circuit, force=True)
        pack_step.assert_called_once()

    def test_skipped_for_a_single_neuron(self, config, pack_step):
        generate_additional_circuit_assets(
            circuit_path=config, circuit_entity=circuit_with(scale="single")
        )
        pack_step.assert_not_called()

    def test_skipped_when_not_requested(self, config, pack_step):
        generate_additional_circuit_assets(
            circuit_path=config, circuit_entity=circuit_with(), include_morphology_pack=False
        )
        pack_step.assert_not_called()

    def test_built_without_the_images(self, config, pack_step):
        generate_additional_circuit_assets(
            circuit_path=config, circuit_entity=circuit_with(), include_overview_images=False
        )
        pack_step.assert_called_once()

    def test_a_failure_is_logged_after_the_other_steps(
        self, config, other_steps, pack_step, caplog
    ):
        pack_step.side_effect = RuntimeError("no room")
        with caplog.at_level(logging.WARNING, logger=generate.L.name):
            generate_additional_circuit_assets(
                circuit_path=config, edge_population="edges", circuit_entity=circuit_with()
            )
        assert all(step.called for step in other_steps)
        assert "Morphology pack asset generation/registration failed: no room" in caplog.text


class TestGenerateMorphologyPackAsset:
    def test_built_and_uploaded(self, tmp_path):
        client, circuit = MagicMock(), circuit_with()
        with patch.object(generate, "add_morphology_pack_asset") as upload:
            pack_file = generate_morphology_pack_asset(
                circuit_path=CONTAINER_CIRCUIT / "circuit_config.json",
                output_dir=tmp_path / "pack",
                client=client,
                circuit_entity=circuit,
            )
        assert pack_file == tmp_path / "pack" / "circuit.mpack"
        assert pack_file.read_bytes().startswith(b"MPCK")
        upload.assert_called_once_with(
            client=client, pack_file=pack_file, registered_circuit=circuit
        )

    def test_none_where_the_circuit_can_have_none(self, tmp_path, caplog):
        with (
            patch(
                "obi_one.scientific.library.morphology_pack.build.build_morphology_pack",
                side_effect=NoPackError("too many"),
            ),
            patch.object(generate, "add_morphology_pack_asset") as upload,
            caplog.at_level(logging.INFO, logger=generate.L.name),
        ):
            pack_file = generate_morphology_pack_asset(
                circuit_path=CONTAINER_CIRCUIT / "circuit_config.json",
                output_dir=tmp_path / "pack",
                client=MagicMock(),
                circuit_entity=circuit_with(),
            )
        assert pack_file is None
        upload.assert_not_called()
        assert "No morphology pack for circuit circuit-1: too many" in caplog.text


def test_the_upload_replaces_any_pack(tmp_path):
    pack_file = tmp_path / "circuit.mpack"
    pack_file.write_bytes(b"MPCK")
    client, circuit = MagicMock(), circuit_with()
    with patch(
        "obi_one.db_sdk.registration.circuit.assets._upload_or_replace_file"
    ) as upload_or_replace:
        add_morphology_pack_asset(client, pack_file, circuit)
    args, kwargs = upload_or_replace.call_args
    assert args == (client, circuit)
    assert kwargs["asset_label"] == AssetLabel.circuit_morphology_pack
    assert kwargs["file_path"] == pack_file
    assert kwargs["file_content_type"] == "application/octet-stream"
    assert isinstance(kwargs["transfer_config"], MultipartUploadTransferConfig)

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from entitysdk import models
from entitysdk.types import AssetLabel

from obi_one.db_sdk import circuit as test_module


def asset(*, asset_id: str, label: AssetLabel | str) -> SimpleNamespace:
    return SimpleNamespace(id=asset_id, label=label)


def circuit(*assets: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(id="circuit-id", assets=list(assets))


class TestCircuitDbHelpers:
    def test_asset_label_value_accepts_enum_and_string(self):
        assert test_module._asset_label_value(AssetLabel.sonata_circuit) == "sonata_circuit"
        assert test_module._asset_label_value("custom") == "custom"

    def test_assets_with_label_filters_enum_and_string_labels(self):
        matching_enum = asset(asset_id="enum", label=AssetLabel.sonata_circuit)
        matching_string = asset(asset_id="string", label="sonata_circuit")
        other = asset(asset_id="other", label="other")

        result = test_module._assets_with_label(
            circuit(matching_enum, matching_string, other),
            AssetLabel.sonata_circuit,
        )

        assert result == [matching_enum, matching_string]
        assert test_module._assets_with_label(circuit(), AssetLabel.sonata_circuit) == []

    def test_delete_assets_with_label_removes_matching_assets(self):
        matching = asset(asset_id="matching", label=AssetLabel.sonata_circuit)
        other = asset(asset_id="other", label="other")
        registered_circuit = circuit(matching, other)
        client = MagicMock()

        test_module._delete_assets_with_label(
            client,
            registered_circuit,
            AssetLabel.sonata_circuit,
        )

        client.delete_asset.assert_called_once_with(
            entity_id="circuit-id",
            entity_type=models.Circuit,
            asset_id="matching",
        )
        assert registered_circuit.assets == [other]

    def test_delete_assets_with_label_handles_assets_becoming_none(self):
        matching = asset(asset_id="matching", label=AssetLabel.sonata_circuit)

        class CircuitWithChangingAssets:
            id = "circuit-id"

            def __init__(self):
                self.access_count = 0

            @property
            def assets(self):
                self.access_count += 1
                return [matching] if self.access_count == 1 else None

        client = MagicMock()
        registered_circuit = CircuitWithChangingAssets()

        test_module._delete_assets_with_label(
            client,
            registered_circuit,
            AssetLabel.sonata_circuit,
        )

        client.delete_asset.assert_called_once()

    def test_upload_or_replace_file_updates_single_existing_asset(self, tmp_path):
        existing = asset(asset_id="existing", label=AssetLabel.sonata_circuit)
        client = MagicMock()
        client.update_asset_file.return_value = existing

        result = test_module._upload_or_replace_file(
            client,
            circuit(existing),
            asset_label=AssetLabel.sonata_circuit,
            file_path=tmp_path / "circuit.json",
            file_content_type="application/json",
        )

        assert result is existing
        client.update_asset_file.assert_called_once()
        client.upload_file.assert_not_called()

    def test_upload_or_replace_file_uploads_when_no_existing_asset(self, tmp_path):
        uploaded = asset(asset_id="uploaded", label=AssetLabel.sonata_circuit)
        client = MagicMock()
        client.upload_file.return_value = uploaded

        result = test_module._upload_or_replace_file(
            client,
            circuit(),
            asset_label=AssetLabel.sonata_circuit,
            file_path=tmp_path / "circuit.json",
            file_content_type="application/json",
        )

        assert result is uploaded
        client.update_asset_file.assert_not_called()
        client.upload_file.assert_called_once()

    def test_upload_or_replace_file_replaces_multiple_existing_assets(self, tmp_path):
        first = asset(asset_id="first", label=AssetLabel.sonata_circuit)
        second = asset(asset_id="second", label=AssetLabel.sonata_circuit)
        uploaded = asset(asset_id="uploaded", label=AssetLabel.sonata_circuit)
        client = MagicMock()
        client.upload_file.return_value = uploaded

        result = test_module._upload_or_replace_file(
            client,
            circuit(first, second),
            asset_label=AssetLabel.sonata_circuit,
            file_path=tmp_path / "circuit.tar.gz",
            file_content_type="application/gzip",
            transfer_config=object(),
        )

        assert result is uploaded
        assert client.delete_asset.call_count == 2
        client.update_asset_file.assert_not_called()
        client.upload_file.assert_called_once()

    def test_upload_or_replace_directory_uploads_without_existing_asset(self, tmp_path):
        uploaded = asset(asset_id="uploaded", label=AssetLabel.sonata_circuit)
        client = MagicMock()
        client.upload_directory.return_value = uploaded

        result = test_module._upload_or_replace_directory(
            client,
            circuit(),
            asset_label=AssetLabel.sonata_circuit,
            name="circuit",
            paths={tmp_path / "circuit.json": Path("circuit.json")},
        )

        assert result is uploaded
        client.delete_asset.assert_not_called()
        client.upload_directory.assert_called_once()

    def test_upload_or_replace_directory_deletes_existing_assets(self):
        existing = asset(asset_id="existing", label=AssetLabel.sonata_circuit)
        uploaded = asset(asset_id="uploaded", label=AssetLabel.sonata_circuit)
        client = MagicMock()
        client.upload_directory.return_value = uploaded

        result = test_module._upload_or_replace_directory(
            client,
            circuit(existing),
            asset_label=AssetLabel.sonata_circuit,
            name="circuit",
            paths={},
        )

        assert result is uploaded
        client.delete_asset.assert_called_once()
        client.upload_directory.assert_called_once()

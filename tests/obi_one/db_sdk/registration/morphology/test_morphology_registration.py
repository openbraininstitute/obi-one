import uuid
from unittest.mock import MagicMock, patch

import pytest
from entitysdk.exception import EntitySDKError
from entitysdk.models import MeasurementAnnotation
from entitysdk.types import AssetLabel

from obi_one.db_sdk.registration.morphology import (
    register_morphology_with_assets_and_metrics,
    register_morphometrics,
    upload_morphology_content,
    upload_morphology_file,
)


def test_upload_morphology_file_unsupported_extension(tmp_path):
    client = MagicMock()
    file_path = tmp_path / "file.xyz"
    file_path.write_bytes(b"data")
    with pytest.raises(ValueError, match="Unsupported file extension"):
        upload_morphology_file(client, uuid.uuid4(), file_path)


def test_upload_morphology_file_entity_sdk_error(tmp_path):
    client = MagicMock()
    client.upload_file.side_effect = EntitySDKError("Network error")
    file_path = tmp_path / "file.swc"
    file_path.write_bytes(b"data")
    with pytest.raises(EntitySDKError):
        upload_morphology_file(client, uuid.uuid4(), file_path)


def test_upload_morphology_content_entity_sdk_error():
    client = MagicMock()
    client.upload_content.side_effect = EntitySDKError("upload failed")
    with pytest.raises(EntitySDKError):
        upload_morphology_content(client, uuid.uuid4(), "file.swc", b"data")


def test_register_morphometrics_success():
    client = MagicMock()
    client.register_entity.return_value = MagicMock(id="result-id")
    result = register_morphometrics(client, uuid.uuid4(), [])
    assert result.id == "result-id"


def test_register_morphometrics_entity_sdk_error():
    client = MagicMock()
    client.register_entity.side_effect = EntitySDKError("Network error")
    with pytest.raises(EntitySDKError):
        register_morphometrics(client, uuid.uuid4(), [])


COMPUTE_MORPHOMETRICS = "obi_one.db_sdk.registration.morphology.register.compute_morphometrics"


@pytest.fixture
def morphology_files(tmp_path):
    files = {}
    for ext in (".swc", ".h5"):
        path = tmp_path / f"morph{ext}"
        path.write_bytes(b"data")
        files[ext] = path
    return files


def test_register_morphology_with_assets_and_metrics(morphology_files, tmp_path):
    client = MagicMock()
    registered = MagicMock(id=uuid.uuid4())
    client.register_entity.return_value = registered
    spines_file = tmp_path / "spines.h5"
    spines_file.write_bytes(b"data")

    with patch(COMPUTE_MORPHOMETRICS, return_value=[]) as compute:
        result = register_morphology_with_assets_and_metrics(
            client,
            MagicMock(),
            morphology_files,
            extra_assets={AssetLabel.morphology_with_spines: spines_file},
        )

    assert result is registered
    compute.assert_called_once_with(morphology_files[".h5"])
    assert client.upload_file.call_count == 3
    assert client.upload_file.call_args.kwargs["asset_label"] == AssetLabel.morphology_with_spines
    measurement = client.register_entity.call_args_list[-1].kwargs["entity"]
    assert isinstance(measurement, MeasurementAnnotation)
    assert measurement.entity_id == registered.id


def test_register_morphology_with_assets_and_metrics_metrics_failure(morphology_files):
    client = MagicMock()
    registered = MagicMock(id=uuid.uuid4())
    client.register_entity.return_value = registered

    with patch(COMPUTE_MORPHOMETRICS, side_effect=RuntimeError("bad morphology")):
        result = register_morphology_with_assets_and_metrics(client, MagicMock(), morphology_files)

    assert result is registered
    client.register_entity.assert_called_once()

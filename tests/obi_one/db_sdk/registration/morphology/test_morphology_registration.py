import uuid
from unittest.mock import MagicMock

import pytest
from entitysdk.exception import EntitySDKError

from obi_one.db_sdk.registration.morphology import (
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

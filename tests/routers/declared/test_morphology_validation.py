import zipfile
from http import HTTPStatus
from io import BytesIO

import pytest

from app.errors import ApiErrorCode

from tests.utils import DATA_DIR

ROUTE = "/declared/test-neuron-file"


def get_error_code(response_json: dict) -> str:
    if isinstance(response_json.get("detail"), dict):
        return response_json["detail"].get("code")
    return response_json.get("code")


def get_error_detail(response_json: dict) -> str:
    if isinstance(response_json.get("detail"), dict):
        return response_json["detail"].get("detail")
    return response_json.get("detail")


@pytest.fixture
def morphology_swc():
    return (DATA_DIR / "cell_morphology.swc").read_bytes()


@pytest.fixture
def morphology_asc():
    return (DATA_DIR / "cell_morphology.asc").read_bytes()


def test_validate_neuron_file_success(client, morphology_swc):
    files = {"file": ("neuron.swc", BytesIO(morphology_swc), "application/octet-stream")}
    response = client.post(ROUTE, files=files)

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(BytesIO(response.content)) as zf:
        names = zf.namelist()
        assert "input.h5" in names
        assert "input.asc" in names


def test_validate_neuron_file_with_single_point_soma(client, morphology_swc):
    files = {"file": ("neuron.swc", BytesIO(morphology_swc), "application/octet-stream")}
    response = client.post(ROUTE, files=files, params={"single_point_soma": True})

    assert response.status_code == HTTPStatus.OK
    with zipfile.ZipFile(BytesIO(response.content)) as zf:
        assert len(zf.namelist()) == 2


def test_validate_neuron_file_invalid_extension(client):
    files = {"file": ("neuron.txt", BytesIO(b"data"), "text/plain")}
    response = client.post(ROUTE, files=files)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert get_error_code(response.json()) == ApiErrorCode.INVALID_REQUEST
    assert "Invalid file extension" in get_error_detail(response.json())


def test_validate_neuron_file_invalid_soma_diameter(client):
    swc_content = b"1 1 0 0 0 150 -1\n"
    files = {"file": ("bad.swc", BytesIO(swc_content), "application/octet-stream")}
    response = client.post(ROUTE, files=files)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert get_error_code(response.json()) == ApiErrorCode.INVALID_REQUEST
    assert "Unrealistic soma diameter" in get_error_detail(response.json())


def test_validate_neuron_file_invalid_morphology(client):
    files = {"file": ("invalid.swc", BytesIO(b"invalid data"), "application/octet-stream")}
    response = client.post(ROUTE, files=files)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "Morphology validation failed" in get_error_detail(response.json())


def test_validate_neuron_file_asc_format(client, morphology_asc):
    files = {"file": ("neuron.asc", BytesIO(morphology_asc), "application/octet-stream")}
    response = client.post(ROUTE, files=files)

    assert response.status_code == HTTPStatus.OK
    with zipfile.ZipFile(BytesIO(response.content)) as zf:
        names = zf.namelist()
        assert "input.swc" in names
        assert "input.h5" in names


def test_validate_neuron_file_empty_file(client):
    files = {"file": ("empty.swc", BytesIO(b""), "application/octet-stream")}
    response = client.post(ROUTE, files=files)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "File size is 0" in get_error_detail(response.json())
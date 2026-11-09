import zipfile
from http import HTTPStatus
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.application import app
from app.errors import ApiErrorCode

from tests.utils import AUTH_HEADER_USER_1, DATA_DIR, PROJECT_HEADERS

ROUTE = "/declared/test-neuron-file"


def get_error_code(response_json: dict) -> str:
    if "error_code" in response_json:
        return response_json["error_code"]
    detail = response_json.get("detail")
    if isinstance(detail, dict):
        return detail["code"]
    return response_json["code"]


def get_error_detail(response_json: dict) -> str:
    if "error_code" in response_json:
        details = response_json.get("details")
        if isinstance(details, dict) and "detail" in details:
            return details["detail"]
        if isinstance(details, list) and details and "msg" in details[0]:
            return details[0]["msg"]
        return response_json["message"]
    detail = response_json.get("detail")
    if isinstance(detail, dict):
        return detail["detail"]
    return response_json["detail"]


@pytest.fixture
def morphology_swc():
    return (DATA_DIR / "minimal_morphology.swc").read_bytes()


@pytest.fixture
def morphology_asc():
    return (DATA_DIR / "minimal_morphology.asc").read_bytes()


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


def test_validate_neuron_file_missing_extension(client):
    files = {"file": ("neuron", BytesIO(b"data"), "text/plain")}
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
    assert get_error_code(response.json()) == ApiErrorCode.INVALID_REQUEST
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


@pytest.mark.usefixtures("_override_check_user_info")
def test_validate_neuron_file_os_error_is_structured_500(morphology_swc, monkeypatch):
    """Server-side conversion failures propagate to the catch-all structured 500.

    FastAPI installs ``Exception`` handlers on ServerErrorMiddleware, which always
    re-raises after writing the response. TestClient must disable
    ``raise_server_exceptions`` to observe that body.
    """

    def _fail(*_args, **_kwargs):
        msg = "No space left on device"
        raise OSError(msg)

    monkeypatch.setattr(
        "app.endpoints.morphology_validation.morphology_service.load_morphio_morphology",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.endpoints.morphology_validation.morphology_service.validate_soma_diameter",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.endpoints.morphology_validation.morphology_service.convert_morphology",
        _fail,
    )

    files = {"file": ("neuron.swc", BytesIO(morphology_swc), "application/octet-stream")}
    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.post(
            ROUTE, files=files, headers={**AUTH_HEADER_USER_1, **PROJECT_HEADERS}
        )

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    body = response.json()
    assert set(body) == {"error_code", "message", "details"}
    assert body["error_code"] == ApiErrorCode.INTERNAL_ERROR
    assert "No space left on device" in body["message"]
    assert "No space left on device" in body["details"][0]["msg"]

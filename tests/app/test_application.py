from http import HTTPStatus

from entitysdk.exception import EntitySDKError

from app.application import app
from app.errors import ApiErrorCode


@app.get("/_test/entitysdk-error")
async def raise_entitysdk_error():
    msg = "DB exploded"
    raise EntitySDKError(msg)


def test_entitysdk_error_is_converted_to_api_error(client, caplog):
    with caplog.at_level("ERROR"):
        response = client.get("/_test/entitysdk-error")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR

    body = response.json()
    assert body["message"] == "DB exploded"
    assert body["error_code"] == ApiErrorCode.DATABASE_CLIENT_ERROR

    expected_msg = "EntitySDKError in GET http://testserver/_test/entitysdk-error"
    log_messages = [r for r in caplog.records if r.getMessage() == expected_msg]
    assert len(log_messages) == 1
    assert log_messages[0].exc_info is not None

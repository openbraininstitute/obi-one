import entitysdk.client
import entitysdk.common
from starlette.requests import Request

from app.config import settings
from app.dependencies.auth import UserContextDep


class FixedTokenManager:
    """A fixed token manager that always returns the same token."""

    def __init__(self, token: str) -> None:
        """Initialize."""
        self._token = token

    def get_token(self) -> str:
        return self._token


def get_client(
    user_context: UserContextDep,
    request: Request,
) -> entitysdk.client.Client:
    if user_context.project_id and user_context.virtual_lab_id:
        project_context = entitysdk.common.ProjectContext(
            project_id=user_context.project_id,
            virtual_lab_id=user_context.virtual_lab_id,
        )
    else:
        project_context = None
    token_manager = FixedTokenManager(user_context.token.credentials)
    client = entitysdk.client.Client(
        api_url=settings.ENTITYCORE_URL,
        project_context=project_context,
        http_client=request.state.http_client,
        token_manager=token_manager,
    )
    return client

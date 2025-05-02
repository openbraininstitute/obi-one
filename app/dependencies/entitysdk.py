import entitysdk.client
import entitysdk.common
from app.config import settings

from app.dependencies.auth import UserContextDep

class FixedTokenManager:
    """
    A fixed token manager that always returns the same token.
    This is used for testing purposes.
    """

    def __init__(self, token: str):
        self._token = token

    def get_token(self) -> str:
        return self._token

from starlette.requests import Request
def get_client(
    user_context: UserContextDep,
    request: Request,
    ) -> entitysdk.client.Client:
    project_context = entitysdk.common.ProjectContext(project_id=user_context.project_id, virtual_lab_id=user_context.virtual_lab_id)
    token_manager = FixedTokenManager(user_context.token.credentials)
    client = entitysdk.client.Client(
        api_url=settings.ENTITYCORE_API_URL, project_context=project_context, 
        http_client=request.state.http_client, token_manager=token_manager, environment=settings.ENVIRONMENT, 
        )
    return client
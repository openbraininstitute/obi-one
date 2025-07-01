from pathlib import Path

from entitysdk.client import Client
from entitysdk.common import ProjectContext
from obi_auth import get_token

class FixedTokenManager:
    """A fixed token manager that always returns the same token."""

    def __init__(self, token: str):
        self._token = token

    def get_token(self) -> str:
        return self._token

class DatabaseManager:
    def __init__(self) -> None:
        """Initialize the DatabaseManager with default values."""
        self.client = None
        self.token = None
        self.entity_file_store_path = None

    def initialize(
        self,
        virtual_lab_id: str,
        project_id: str,
        entity_file_store_root: Path = Path("../../obi-output"),
        entitycore_api_url: str | None = None, # If None, it will use the default from settings.ENTITYCORE_URL
    ) -> None:
        """Initialize the database connection and set up the file store path."""
        self.entity_file_store_path = entity_file_store_root / "obi-entity-file-store"

        self.entity_file_store_path.mkdir(parents=True, exist_ok=True)

        # Staging
        self.token = get_token(environment="staging")
        project_context = ProjectContext(virtual_lab_id=virtual_lab_id, project_id=project_id)

        # self.token.credentials
        token_manager = FixedTokenManager(self.token)

        if entitycore_api_url is None:
            entitycore_api_url = settings.ENTITYCORE_URL

        self.client = Client(
            api_url=entitycore_api_url,
            project_context=project_context,
            token_manager=token_manager,
        )

        """
        Local. Not fully working
        project_context = ProjectContext(virtual_lab_id=virtual_lab_id, project_id=project_id)
        self.client = Client(api_url=entitycore_api_url, project_context=project_context)
        self.token = os.getenv("ACCESS_TOKEN", "XXX")
        """


db = DatabaseManager()

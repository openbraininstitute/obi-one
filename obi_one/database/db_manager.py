from pathlib import Path

from entitysdk.client import Client
from entitysdk.common import ProjectContext
from obi_auth import get_token


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
        entitycore_api_url: str = "http://127.0.0.1:8000",
    ) -> None:
        """Initialize the database connection and set up the file store path."""
        self.entity_file_store_path = entity_file_store_root / "obi-entity-file-store"

        self.entity_file_store_path.mkdir(parents=True, exist_ok=True)

        # Staging
        self.token = get_token(environment="staging")
        project_context = ProjectContext(virtual_lab_id=virtual_lab_id, project_id=project_id)

        self.client = Client(api_url=entitycore_api_url, project_context=project_context)

        """
        Local. Not fully working
        project_context = ProjectContext(virtual_lab_id=virtual_lab_id, project_id=project_id)
        self.client = Client(api_url=entitycore_api_url, project_context=project_context)
        self.token = os.getenv("ACCESS_TOKEN", "XXX")
        """


db = DatabaseManager()

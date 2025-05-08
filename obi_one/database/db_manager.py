import os

from entitysdk.client import Client
from entitysdk.common import ProjectContext
from obi_auth import get_token


class DatabaseManager:
    def __init__(self):
        self.client = None
        self.token = None
        self.entity_file_store_path = None

    def initialize(
        self,
        virtual_lab_id,
        project_id,
        entity_file_store_root="../../obi-output",
        entitycore_api_url="http://127.0.0.1:8000",
    ):
        """Initialize the database connection and set up the file store path.
        """
        self.entity_file_store_path = entity_file_store_root + "/obi-entity-file-store"
        os.makedirs(self.entity_file_store_path, exist_ok=True)

        # Staging
        self.token = get_token(environment="staging")
        project_context = ProjectContext.from_vlab_url(
            f"https://staging.openbraininstitute.org/app/virtual-lab/lab/{virtual_lab_id}/project/{project_id}/home"
        )
        self.client = Client(environment="staging", project_context=project_context)

        # Local. Not fully working
        # project_context = ProjectContext(virtual_lab_id=virtual_lab_id, project_id=project_id)
        # self.client = Client(api_url=entitycore_api_url, project_context=project_context)
        # self.token = os.getenv("ACCESS_TOKEN", "XXX")


db = DatabaseManager()

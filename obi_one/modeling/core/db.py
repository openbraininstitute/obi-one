import io
import os
import tempfile
from pathlib import Path

# from rich import print as rprint

from entitysdk.client import Client
from entitysdk.common import ProjectContext
from entitysdk.models.entity import Entity
from entitysdk.models.core import Struct
import inspect
from entitysdk.models.morphology import (
    BrainLocation,
    BrainRegion,
    ReconstructionMorphology,
    Species,
    Strain,
)

from obi_auth import get_token

client = None
# token = None
def init_db(virtual_lab_id, project_id, entitycore_api_url="http://127.0.0.1:8000"):
    project_context = ProjectContext(
        virtual_lab_id=virtual_lab_id,
        project_id=project_id,
    )
    global client
    client = Client(api_url=entitycore_api_url, project_context=project_context)

    global token
    token = os.getenv("ACCESS_TOKEN", get_token(environment="staging"))

# Iterate through all imported classes in the current module
imported_classes = [
    obj
    for name, obj in globals().items()
    if inspect.isclass(obj) and obj.__module__ != "__main__"
]


entitysdk_classes = []
for cls in imported_classes:
    # Check if the class inherits from Entity
    if issubclass(cls, Entity) and cls is not Entity:

        # print(cls)
        # Dynamically add the 'find' method to the class
        def find(cls, limit=10, **kwargs): # token=None, 
            return client.search_entity(
                entity_type=cls, query=kwargs, token=token, limit=limit
            ).all()
        setattr(cls, "find", classmethod(find))

        def fetch(cls, entity_id):
            return client.get_entity(
                entity_id=entity_id, entity_type=cls, token=token
            )
        setattr(cls, "fetch", classmethod(fetch))

        # Dynamically add the class to the package
        entitysdk_classes.append(cls)

        # setattr(cls, "__package__", __package__)

    # Check if the class inherits from Struct
    if issubclass(cls, Struct) and cls is not Struct:
        print(cls)

        # setattr(cls, "__package__", __package__)
        entitysdk_classes.append(cls)
        


def download_morphology_assets(morphology):

    for asset in morphology.assets:
        print(asset)
        if asset.content_type == "application/swc":
            client.download_file(
                entity_id=morphology.id,
                entity_type=type(morphology),
                asset_id=asset.id,
                output_path="./my-file.h5",
                token=token,
            )
        #     content = client.download_content(
        #         entity_id=morphology.id, entity_type=type(morphology), asset_id=asset.id, token=token
        #     )
        #     break

        #     print(content)
        #     print(Path("my-file.h5").read_text())

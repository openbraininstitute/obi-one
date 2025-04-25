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

default_base_store = "../obi-output/obi-entity-file-store"

client = None
token = None
entity_file_store_path = None
def init_db(virtual_lab_id, project_id, entity_file_store_root='', entitycore_api_url="http://127.0.0.1:8000"):

    global client
    global token
    global entity_file_store_path

    entity_file_store_path = entity_file_store_root + "/obi-entity-file-store"
    os.makedirs(entity_file_store_path, exist_ok=True)
    
    # # Local. Not fully working
    # project_context = ProjectContext(
    #     virtual_lab_id=virtual_lab_id,
    #     project_id=project_id,
    # )    
    # client = Client(api_url=entitycore_api_url, project_context=project_context)
    # token = os.getenv("ACCESS_TOKEN", "XXX")

    # Staging
    from obi_auth import get_token
    token = get_token(environment="staging")
    # Replace this with your vlab project url in staging
    project_context = ProjectContext.from_vlab_url(f"https://staging.openbraininstitute.org/app/virtual-lab/lab/{virtual_lab_id}/project/{project_id}/home")
    client = Client(environment="staging", project_context=project_context)


# Iterate through all imported classes in the current module
imported_classes = [
    obj
    for name, obj in globals().items()
    if inspect.isclass(obj) and obj.__module__ != "__main__"
]


def make_new_init(cls, original_init):
    def new_init(self, entity_id, *args, **kwargs):
        print("cls: ", cls)
        fetched_entity = cls.fetch(entity_id)
        self.__dict__.update(fetched_entity.__dict__)
        original_init(self, *args, **kwargs)
    return new_init


from typing import Any
from pydantic import BaseModel, Field
from pydantic_core import core_schema
from entitysdk.models.entity import Entity

from typing import Any
from pydantic import BaseModel, Field
from pydantic_core import core_schema
from entitysdk.models.entity import Entity

from typing import Any
from pydantic import BaseModel, Field, create_model
from pydantic_core import core_schema
from pydantic import ConfigDict

from typing import Any
from pydantic import BaseModel, Field, create_model, ConfigDict

from pydantic import BaseModel, Field, create_model, ConfigDict

def make_new_subclass_with_hydration(cls):
    subclass_name = f"{cls.__name__}FromID"

    NewCls = create_model(
        subclass_name,
        id_str=(str, Field(..., description="The ID of the entity in string format.")),
        __config__=ConfigDict(arbitrary_types_allowed=True, extra='allow'),
    )

    original_init = NewCls.__init__

    def __init__(self, **data):
        original_init(self, **data)
        entity = cls.fetch(self.id_str)
        for key, value in entity.dict().items():
            if key != "id_str":
                setattr(self, key, value)
        self._entitysdk_type = cls

    NewCls.__init__ = __init__

    @property
    def entitysdk_type(self):
        return self._entitysdk_type

    NewCls.entitysdk_type = entitysdk_type
    NewCls.__module__ = cls.__module__
    return NewCls
    return NewCls


entitysdk_classes = []
for cls in imported_classes:
    # Check if the class inherits from Entity
    if issubclass(cls, Entity) and cls is not Entity:

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

        subclass = make_new_subclass_with_hydration(cls)
        globals()[subclass.__name__] = subclass
        entitysdk_classes.append(subclass)
        entitysdk_classes.append(cls)



    # Check if the class inherits from Struct
    if issubclass(cls, Struct) and cls is not Struct:
        entitysdk_classes.append(cls)
        

def temporary_download_swc(self):

    for asset in self.assets:
        print(asset)
        print(asset.keys())
        if asset['content_type'] == "application/asc":

            file_output_path = Path(entity_file_store_path) / asset.full_path
            file_output_path.parent.mkdir(parents=True, exist_ok=True)

            client.download_file(
                entity_id=self.id,
                # entity_type=type(self),
                entity_type=self.entitysdk_type,
                asset_id=asset.id,
                output_path=file_output_path,
                token=token,
            )

            return file_output_path
            # self.swc_path = file_output_path
        break
    


ReconstructionMorphology.temporary_download_swc = temporary_download_swc
ReconstructionMorphologyFromID.temporary_download_swc = temporary_download_swc
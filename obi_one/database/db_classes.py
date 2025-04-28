from pathlib import Path
import inspect
from entitysdk.models.entity import Entity
from entitysdk.models.core import Struct
from entitysdk.models.morphology import (
    BrainLocation,
    BrainRegion,
    ReconstructionMorphology,
    Species,
    Strain,
)

from obi_one.database.db_manager import db


"""
Get all imported classes in the current module
"""
entity_classes = []
struct_classes = []
global_values = list(globals().values())
for val in global_values:
    
    if inspect.isclass(val):
        if issubclass(val, Entity):
            entity_classes.append(val)
        if issubclass(val, Struct):
            struct_classes.append(val)

"""
Add the find and fetch methods to all classes that inherit from Entity
Create a new subclass with hydration
"""
db_classes = []
db_classes.extend(struct_classes)


"""
Function to create a new subclass with hydration
"""
from pydantic import Field, create_model, ConfigDict
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


for cls in entity_classes:

    def find(cls, limit=10, **kwargs):
        return db.client.search_entity(
            entity_type=cls, query=kwargs, token=db.token, limit=limit
        ).all()
    setattr(cls, "find", classmethod(find))

    def fetch(cls, entity_id):
        return db.client.get_entity(
            entity_id=entity_id, entity_type=cls, token=db.token
        )
    setattr(cls, "fetch", classmethod(fetch))

    subclass = make_new_subclass_with_hydration(cls)
    globals()[subclass.__name__] = subclass
    db_classes.append(subclass)
    db_classes.append(cls)


def temporary_download_swc(self):

    for asset in self.assets:
        if asset['content_type'] == "application/asc":

            file_output_path = Path(db.entity_file_store_path) / asset['full_path']
            file_output_path.parent.mkdir(parents=True, exist_ok=True)

            entity_type = type(self)
            if hasattr(self, 'entitysdk_type'):
                entity_type = self.entitysdk_type
            

            db.client.download_file(
                entity_id=self.id,
                entity_type=entity_type,
                asset_id=asset['id'],
                output_path=file_output_path,
                token=db.token,
            )

            return file_output_path
        break
    

ReconstructionMorphology.temporary_download_swc = temporary_download_swc
ReconstructionMorphologyFromID.temporary_download_swc = temporary_download_swc
from pathlib import Path
import inspect

from entitysdk.models.entity import Entity
from entitysdk.models.core import Struct
from entitysdk.models.mtype import MTypeClass
from entitysdk.models.morphology import (
    BrainLocation,
    BrainRegion,
    ReconstructionMorphology,
    Species,
    Strain,
    License,
    Taxonomy
)

from obi_one.database.db_manager import db


"""
Get all entity and struct classes from entitysdk
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
Begin db_classes list for module exposure.
Add entitysdk Structs to the list.
"""
db_classes = []
db_classes.extend(struct_classes)


"""
Function to create for a given entitysdk class [ENTITY_CLASS], 
a new class for [ENTITY_CLASS]FromID


"""
from pydantic import Field, create_model, ConfigDict
def create_from_id_class_by_hydration_for_entitysdk_class(cls):

    # The new class name
    new_cls_name = f"{cls.__name__}FromID"

    # Create the new class 
    # With a single id_str field
    new_cls = create_model(
        new_cls_name,
        id_str=(str, Field(..., description="The ID of the entity in string format.")),
        __config__=ConfigDict(arbitrary_types_allowed=True, extra='allow'),
    )

    # Store the original initializer of the new class
    # So it can be called in the new initializer
    original_init = new_cls.__init__

    # Define the new initializer
    def __init__(self, **data):

        # Call the original initializer
        original_init(self, **data)

        # Fetch the entity from the database
        entity = cls.fetch(self.id_str)

        # Add each attribute of the entity to the new class
        for key, value in entity.dict().items():
            if key != "id_str":
                setattr(self, key, value)

        # Add the entitysdk type to the new class
        self._entitysdk_type = cls

    # Set the new initializer
    new_cls.__init__ = __init__


    # Add a property to get the original entitysdk type
    @property
    def entitysdk_type(self):
        return self._entitysdk_type
    new_cls.entitysdk_type = entitysdk_type

    # Set the module of the new class
    new_cls.__module__ = cls.__module__

    return new_cls


"""
Iterate through entitysdk Entity classes
- Add find and fetch methods to each class.
- Create a new class [ENTITY_CLASS]FromID with hydration for each class.
- Add the new class to the db_classes list and globals.
- Add the original class to the db_classes list.
"""
for cls in entity_classes:

    # Add a find method to the class
    # This method will search for entities of the class
    # and can be called as ClassName.find(), ClassName.find(limit=5) or ClassName.find(kwargs=kwargs)
    def find(cls, limit=10, **kwargs):
        return db.client.search_entity(
            entity_type=cls, query=kwargs, token=db.token, limit=limit
        ).all()
    setattr(cls, "find", classmethod(find))


    # Add a fetch method to the class
    # This method will fetch a single entity of the class
    # and can be called as ClassName.fetch(entity_id)
    def fetch(cls, entity_id):
        return db.client.get_entity(
            entity_id=entity_id, entity_type=cls, token=db.token
        )
    setattr(cls, "fetch", classmethod(fetch))

    # Create a new class [ENTITY_CLASS]FromID with hydration for the class.
    new_cls = create_from_id_class_by_hydration_for_entitysdk_class(cls)

    # Add the new_cls to the globals
    globals()[new_cls.__name__] = new_cls

    # Add the original class and new class to the db_classes list
    db_classes.append(new_cls)
    db_classes.append(cls)


"""
Temporary function for downloading SWC files of a morphology
"""
def temporary_download_swc(morphology):

    for asset in morphology.assets:
        if asset['content_type'] == "application/asc":

            file_output_path = Path(db.entity_file_store_path) / asset['full_path']
            file_output_path.parent.mkdir(parents=True, exist_ok=True)

            entity_type = type(morphology)
            if hasattr(morphology, 'entitysdk_type'):
                entity_type = morphology.entitysdk_type
            

            db.client.download_file(
                entity_id=morphology.id,
                entity_type=entity_type,
                asset_id=asset['id'],
                output_path=file_output_path,
                token=db.token,
            )

            return file_output_path
        break
    

"""
Add the temporary download function to the Morphology classes
"""
ReconstructionMorphology.temporary_download_swc = temporary_download_swc
ReconstructionMorphologyFromID.temporary_download_swc = temporary_download_swc
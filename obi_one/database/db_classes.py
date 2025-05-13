import inspect
from pathlib import Path

from entitysdk.models.core import Struct
from entitysdk.models.entity import Entity
from entitysdk.models.morphology import (
    ReconstructionMorphology,
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


from neurom import load_morphology
from pydantic import BaseModel, ConfigDict, Field, create_model


def create_from_id_class_for_entitysdk_class(cls: type[Entity]) -> type[BaseModel]:
    """Given an EntitySDK class, create a new Pydantic model [EntityClassName]FromID
    that initializes from an id_str, fetches the full entity from the database,
    and populates its attributes.
    """
    # New class name
    new_cls_name = f"{cls.__name__}FromID"

    # Create a basic Pydantic model with just id_str
    new_cls = create_model(
        new_cls_name,
        id_str=(str, Field(..., description="ID of the entity in string format.")),
        __config__=ConfigDict(arbitrary_types_allowed=True, extra="allow"),
    )

    # Store original __init__
    original_init = new_cls.__init__

    def __init__(self, **data):
        # Call the original __init__ (to set id_str)
        original_init(self, **data)

        # Fetch the full entity only once
        entity = cls.fetch(self.id_str)

        # Hydrate all attributes except id_str
        for key, value in entity.dict().items():
            if key != "id_str":
                setattr(self, key, value)

        # Save original entity class reference
        self._entitysdk_type = cls

    # Replace the __init__ method
    new_cls.__init__ = __init__

    # Add a property for accessing original class
    @property
    def entitysdk_type(self):
        return self._entitysdk_type

    new_cls.entitysdk_type = entitysdk_type

    # Assign the same module to make debugging and imports easier
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

    cls.find = classmethod(find)

    # Add a fetch method to the class
    # This method will fetch a single entity of the class
    # and can be called as ClassName.fetch(entity_id)
    def fetch(cls, entity_id):
        return db.client.get_entity(entity_id=entity_id, entity_type=cls, token=db.token)

    cls.fetch = classmethod(fetch)

    # Create a new class [ENTITY_CLASS]FromID with hydration for the class.
    new_cls = create_from_id_class_for_entitysdk_class(cls)

    # Add the new_cls to the globals
    globals()[new_cls.__name__] = new_cls

    # Add the original class and new class to the db_classes list
    db_classes.append(new_cls)
    db_classes.append(cls)


def download_swc(morphology):
    """Temporary function for downloading SWC files of a morphology"""
    for asset in morphology.assets:
        if asset["content_type"] == "application/asc":
            file_output_path = Path(db.entity_file_store_path) / asset["full_path"]
            file_output_path.parent.mkdir(parents=True, exist_ok=True)

            entity_type = type(morphology)
            if hasattr(morphology, "entitysdk_type"):
                entity_type = morphology.entitysdk_type

            db.client.download_file(
                entity_id=morphology.id,
                entity_type=entity_type,
                asset_id=asset["id"],
                output_path=file_output_path,
                token=db.token,
            )

            return file_output_path
        break


"""
Add the swc_file property to the Morphology classes
"""
ReconstructionMorphology.swc_file = property(download_swc)
ReconstructionMorphologyFromID.swc_file = property(download_swc)


def neurom_morphology_getter(self):
    """Getter for the neurom_morphology property.
    Downloads the application/asc asset if not already downloaded
    and loads it using neurom.load_morphology.
    """
    if not hasattr(self, "_neurom_morphology"):
        swc_file = self.swc_file
        if swc_file:
            self._neurom_morphology = load_morphology(swc_file)
        else:
            msg = "No valid application/asc asset found for morphology."
            raise ValueError(msg)
    return self._neurom_morphology


def morphio_morphology_getter(self):
    """Getter for the morphio_morphology property.
    Downloads the application/asc asset if not already downloaded
    and initializes it as morphio.Morphology([...]).
    """
    if not hasattr(self, "_morphio_morphology"):
        swc_file = self.swc_file
        if swc_file:
            from morphio import Morphology

            self._morphio_morphology = Morphology(swc_file)
        else:
            raise ValueError("No valid application/asc asset found for morphology.")
    return self._morphio_morphology


"""
Add the neurom_morphology property to the classes
"""
ReconstructionMorphology.neurom_morphology = property(neurom_morphology_getter)
ReconstructionMorphologyFromID.neurom_morphology = property(neurom_morphology_getter)
"""
Add the morphio_morphology property to the classes
"""
ReconstructionMorphology.morphio_morphology = property(morphio_morphology_getter)
ReconstructionMorphologyFromID.morphio_morphology = property(morphio_morphology_getter)

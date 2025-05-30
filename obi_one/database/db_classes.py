import inspect
from pathlib import Path

from entitysdk.models.core import Struct
from entitysdk.models.entity import Entity
from morphio import Morphology
from neurom import load_morphology
from pydantic import BaseModel, Field, PrivateAttr, create_model

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


def create_from_id_class_for_entitysdk_class(cls: type[Entity]) -> type[BaseModel]:
    """Given an EntitySDK class, create a new Pydantic model [EntityClassName]FromID."""

    class EntityFromIDBase(BaseModel):
        _entity: cls | None = PrivateAttr(default=None)

        @property
        def entity(self):
            if self._entity is None:
                self._entity = cls.fetch(self.id_str)
            return self._entity

    # New class name
    new_cls_name = f"{cls.__name__}FromID"

    # Create a new Pydantic model with id_str and base class EntityFromIDBase
    new_cls = create_model(
        new_cls_name,
        id_str=(str, Field(..., description="ID of the entity in string format.")),
        __base__=EntityFromIDBase,
    )

    @property
    def entity(self):
        """Property to access the original entity class."""
        if self._entity is None:
            self._entity = cls.fetch(self.id_str)
        return self._entity

    new_cls.entity = entity

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
    # and can be called as ClassName.find(), ClassName.find(limit=5)
    # or ClassName.find(kwargs=kwargs)
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
    """Temporary function for downloading SWC files of a morphology."""
    for asset in morphology.entity.assets:
        if asset.content_type == "application/asc":
            file_output_path = Path(db.entity_file_store_path) / asset.full_path
            file_output_path.parent.mkdir(parents=True, exist_ok=True)

            entity_type = type(morphology.entity)
            if hasattr(morphology, "entitysdk_type"):
                entity_type = morphology.entitysdk_type

            db.client.download_file(
                entity_id=morphology.entity.id,
                entity_type=entity_type,
                asset_id=asset.id,
                output_path=file_output_path,
                token=db.token,
            )

            return file_output_path


"""
Add the swc_file property to the Morphology classes
"""
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
            self._morphio_morphology = Morphology(swc_file)
        else:
            raise ValueError("No valid application/asc asset found for morphology.")
    return self._morphio_morphology


"""
Add the neurom_morphology property to the classes
"""
ReconstructionMorphologyFromID.neurom_morphology = property(neurom_morphology_getter)

"""
Add the morphio_morphology property to the classes
"""
ReconstructionMorphologyFromID.morphio_morphology = property(morphio_morphology_getter)

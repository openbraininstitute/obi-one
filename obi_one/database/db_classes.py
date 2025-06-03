import inspect
from pathlib import Path

from entitysdk.models.core import Struct
from entitysdk.models.entity import Entity
from morphio import Morphology
from neurom import load_morphology
from pydantic import BaseModel, Field, PrivateAttr, create_model

import abc

from obi_one.database.db_manager import db

from entitysdk.models import (
    ReconstructionMorphology,
)

# """
# Get all entity and struct classes from entitysdk
# """
# entity_classes = []
# struct_classes = []
# global_values = list(globals().values())
# for val in global_values:
#     if inspect.isclass(val):
#         if issubclass(val, Entity):
#             entity_classes.append(val)
#         if issubclass(val, Struct):
#             struct_classes.append(val)


# """
# Begin db_classes list for module exposure.
# Add entitysdk Structs to the list.
# """
# db_classes = []
# db_classes.extend(struct_classes)


from typing import Type, Optional, Generic, TypeVar, ClassVar
from pydantic import BaseModel, PrivateAttr, Field
import abc

class EntityFromID(BaseModel, abc.ABC):
    entitysdk_class: ClassVar[Type[Entity]] = None
    id_str: str = Field(..., description="ID of the entity in string format.")
    _entity: Optional[Entity] = PrivateAttr(default=None)
    
    @classmethod
    def fetch(cls, entity_id: str):
        return db.client.get_entity(
            entity_id=entity_id,
            entity_type=cls.entitysdk_class,
            token=db.token
        )

    @property
    def entity(self):
        print(self.__class__.entitysdk_class)
        if self._entity is None:
            self._entity = self.__class__.fetch(self.id_str)
        return self._entity

    @property
    def entitysdk_type(self) -> Type[Entity]:
        return self.__class__.entitysdk_class


class ReconstructionMorphologyFromID(EntityFromID):
    entitysdk_class: ClassVar[Type[Entity]] = ReconstructionMorphology
    _entity: Optional[ReconstructionMorphology] = PrivateAttr(default=None)
    _swc_file_path: Optional[Path] = PrivateAttr(default=None)
    

    @property
    def swc_file(self):
        """Function for downloading SWC files of a morphology."""

        if self._swc_file_path is None:
            for asset in self.entity.assets:
                if asset.content_type == "application/asc":
                    file_output_path = Path(db.entity_file_store_path) / asset.full_path
                    file_output_path.parent.mkdir(parents=True, exist_ok=True)

                    db.client.download_file(
                        entity_id=self.entity.id,
                        entity_type=self.entitysdk_type,
                        asset_id=asset.id,
                        output_path=file_output_path,
                        token=db.token,
                    )

                    self._swc_file_path = file_output_path
                    break

        return self._swc_file_path


    # @property
    # def neurom_morphology(self):
    #     """Getter for the neurom_morphology property.

    #     Downloads the application/asc asset if not already downloaded
    #     and loads it using neurom.load_morphology.
    #     """
    #     if not hasattr(self, "_neurom_morphology"):
    #         swc_file = self.swc_file
    #         if swc_file:
    #             self._neurom_morphology = load_morphology(swc_file)
    #         else:
    #             msg = "No valid application/asc asset found for morphology."
    #             raise ValueError(msg)
    #     return self._neurom_morphology

    # @property
    # def morphio_morphology(self):
    #     """Getter for the morphio_morphology property.

    #     Downloads the application/asc asset if not already downloaded
    #     and initializes it as morphio.Morphology([...]).
    #     """
    #     if not hasattr(self, "_morphio_morphology"):
    #         swc_file = self.swc_file
    #         if swc_file:
    #             self._morphio_morphology = Morphology(swc_file)
    #         else:
    #             raise ValueError("No valid application/asc asset found for morphology.")
    #     return self._morphio_morphology



# """
# Iterate through entitysdk Entity classes
# - Add find and fetch methods to each class.
# - Create a new class [ENTITY_CLASS]FromID with hydration for each class.
# - Add the new class to the db_classes list and globals.
# - Add the original class to the db_classes list.
# """
# for cls in entity_classes:
#     # Add a find method to the class
#     # This method will search for entities of the class
#     # and can be called as ClassName.find(), ClassName.find(limit=5)
#     # or ClassName.find(kwargs=kwargs)
#     def find(cls, limit=10, **kwargs):
#         return db.client.search_entity(
#             entity_type=cls, query=kwargs, token=db.token, limit=limit
#         ).all()

#     cls.find = classmethod(find)

    # # Add a fetch method to the class
    # # This method will fetch a single entity of the class
    # # and can be called as ClassName.fetch(entity_id)
    # def fetch(cls, entity_id):
    #     return db.client.get_entity(entity_id=entity_id, entity_type=cls, token=db.token)

    # cls.fetch = classmethod(fetch)

#     # Create a new class [ENTITY_CLASS]FromID with hydration for the class.
#     new_cls = create_from_id_class_for_entitysdk_class(cls)

#     # Add the new_cls to the globals
#     globals()[new_cls.__name__] = new_cls

#     # Add the original class and new class to the db_classes list
#     db_classes.append(new_cls)
#     db_classes.append(cls)



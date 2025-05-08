from typing import ClassVar

from obi_one.core.base import OBIBaseModel


class Form(OBIBaseModel):
    """ """

    name: ClassVar[str] = "Add a name class' name variable"
    description: ClassVar[str] = """Add a description to the class' description variable"""
    single_coord_class_name: ClassVar[str] = ""

    def cast_to_single_coord(self):
        module = __import__(self.__module__)
        class_to_cast_to = getattr(module, self.single_coord_class_name)
        single_coord = class_to_cast_to.model_construct(**self.__dict__)
        return single_coord

    @property
    def single_coord_scan_default_subpath(self):
        return self.single_coord_class_name + "/"

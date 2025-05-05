from pydantic import PrivateAttr
from obi.modeling.core.base import OBIBaseModel

class Form(OBIBaseModel):
    """
    """
    _single_coord_class_name: str = ""

    def cast_to_single_coord(self):
        module = __import__(self.__module__)
        class_to_cast_to = getattr(module, self._single_coord_class_name)
        single_coord = class_to_cast_to.model_construct(**self.__dict__)
        return single_coord
    
    @property
    def single_coord_scan_default_subpath(self):
        return self._single_coord_class_name + "/"

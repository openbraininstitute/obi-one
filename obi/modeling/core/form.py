from pydantic import PrivateAttr
from obi.modeling.core.base import OBIBaseModel

class Form(OBIBaseModel):
    """
    """
    _sonata_config: dict = PrivateAttr(default={})
    _single_coord_class_name: str = ""

    
    # def __init_subclass__(cls, **kwargs):
    #     super().__init_subclass__(**kwargs)
    #     if not hasattr(cls, 'single_coord_class_name'):
    #         raise NotImplementedError(f"{cls.__name__} must implement 'single_coord_class_name'")
    # single_coord_class_name: str = ''

    def cast_to_single_coord(self):
        module = __import__(self.__module__)
        class_to_cast_to = getattr(module, self.single_coord_class_name)
        single_coord = class_to_cast_to.model_construct(**self.__dict__)
        return single_coord
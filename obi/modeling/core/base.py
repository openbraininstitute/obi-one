"""
Adapted from https://github.com/pydantic/pydantic/issues/7366
"""


from pydantic import BaseModel, model_serializer, model_validator, ValidatorFunctionWrapHandler
from typing import Any, Dict, List, Type, TypeVar

T = TypeVar('T')

def get_subclasses_recursive(cls: Type[T]) -> List[Type[T]]:
    """
    Returns all the subclasses of a given class.
    """
    subclasses = []
    for subclass in cls.__subclasses__():
        subclasses.append(subclass)
        subclasses.extend(get_subclasses_recursive(subclass))
    return subclasses


def get_subclass_recursive(cls: Type[T], name: str, allow_same_class: bool = False) -> Type[T]:
    # I oversimplified this to keep it short (there are checks for 0 or more than 1 subclasses
    # and we did not even use parameter `allow_same_class` to also match the parent class) 
    return next(c for c in get_subclasses_recursive(cls=cls) if c.__name__ == name)

class OBIBaseModel(BaseModel):

    def __str__(self):
        return self.__repr__()


    """
    Preserves the types of objects passed in pydantic models during serialization and de-serialization.
    This is achieved by injecting a field called "type" upon serialization.
    """

    @model_serializer(mode='wrap')
    def inject_type_on_serialization(self, handler: ValidatorFunctionWrapHandler) -> Dict[str, Any]:
        result: Dict[str, Any] = handler(self)
        # if 'obi_class' in result:
        #     raise ValueError('Cannot use field "obi_class". It is reserved.')
        result['obi_class'] = f'{self.__class__.__name__}'
        return result

    @model_validator(mode='wrap')  # noqa  # the decorator position is correct
    @classmethod
    def retrieve_type_on_deserialization(cls, value: Any,
                                         handler: ValidatorFunctionWrapHandler) -> 'OBIBaseModel':
        if isinstance(value, dict):
            # WARNING: we do not want to modify `value` which will come from the outer scope
            # WARNING2: `sub_cls(**modified_value)` will trigger a recursion, and thus we need to remove `obi_class`
            modified_value = value.copy()
            sub_cls_name = modified_value.pop('obi_class', None)
            if sub_cls_name is not None:
                sub_cls = get_subclass_recursive(cls=OBIBaseModel, name=sub_cls_name, allow_same_class=True)
                return sub_cls(**modified_value)
            else:
                return handler(value)
        return handler(value)

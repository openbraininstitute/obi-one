from .template import SubTemplate
from typing import Union, List

class Stimulus(SubTemplate):
    """A nested model containing numeric attributes."""
    nested_param1: Union[float, List[float]]
    nested_param2: Union[float, List[float]]
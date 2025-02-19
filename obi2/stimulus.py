from .multi_template import MultiTemplate
from typing import Union, List

class Stimulus(MultiTemplate):
    """A nested model containing numeric attributes."""
    nested_param1: Union[float, List[float]]
    nested_param2: Union[float, List[float]]
from .multi_template import MultiTemplate, SingleTypeMixin
from .stimulus import Stimulus

from pydantic import PrivateAttr

class SimulationCampaignTemplate(MultiTemplate):
    """Base simulation model that contains a generic nested object."""
    nested: dict[str, Stimulus]

    # Is this reasonable? (Is there an alternative?)
    def single_version_class(self):
        return globals()["Simulation"] 


class Simulation(SimulationCampaignTemplate, SingleTypeMixin):
    """Only allows single float values and ensures nested attributes follow the same rule."""
    pass

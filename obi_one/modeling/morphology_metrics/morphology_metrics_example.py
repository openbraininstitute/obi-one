from typing import Union
from typing import ClassVar

from obi_one.core.form import Form
from obi_one.core.block import Block
from obi_one.core.single import SingleCoordinateMixin
from obi_one.core.path import NamedPath
from obi_one.core.base import OBIBaseModel
from obi_one.database.db_classes import *




class MorphologyMetricsExampleForm(Form):
    """
    """

    single_coord_class_name: ClassVar[str] = "MorphologyMetricsExample"
    name: ClassVar[str] = "Morphology metrics example name"
    description: ClassVar[str] = """Add a description of the tool to the classes description variable"""

    class Initialize(Block):
        morphology: ReconstructionMorphology | ReconstructionMorphologyFromID | list[Union[ReconstructionMorphology, ReconstructionMorphologyFromID]]

    initialize: Initialize

    def save(self, circuit_entities):
        """
        Add entitysdk calls to save the collection
        """
        pass


class MorphologyMetricsExampleRunOutput(OBIBaseModel):
    features: dict = Field(
    default_factory=dict,
    description="Dictionary containing feature_name: value.",
)



import traceback
import neurom
import numpy as np
class MorphologyMetricsExample(MorphologyMetricsExampleForm, SingleCoordinateMixin):
    """
    Code orgininally created for https://github.com/openbraininstitute/neuroagent by:
    Boris Bergsma, Nicolas Frank, Jan Krepl
    in https://github.com/openbraininstitute/neuroagent/blob/main/backend/src/neuroagent/tools/morphology_features_tool.py
    """


    def run(self) -> MorphologyMetricsExampleRunOutput:
        
        try:
            self.features = {
                "soma_radius [µm]": neurom.get("soma_radius", self.initialize.morphology.neurom_morphology),
                "soma_surface_area [µm^2]": neurom.get("soma_surface_area", self.initialize.morphology.neurom_morphology),
            }

        except Exception as e:
            traceback.print_exception(e)
            
        

    def save(self):
        """
        Add entitysdk calls to save the single instance
        """
        pass        

    def data() -> MorphologyMetricsExampleRunOutput:
        """
        Return the data to the client
        """
        return MorphologyMetricsExampleRunOutput(features=self.features)
        

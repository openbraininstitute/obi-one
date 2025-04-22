from obi_one.core.form import Form
from obi_one.core.block import Block
from obi_one.core.single import SingleCoordinateMixin
# from obi_one.core.db import SaveCircuitEntity, SaveCircuitCollectionEntity
from obi_one.core.path import NamedPath

from obi_one.core.db import *

class SingleBlockGenerateTestForm(Form):
    """
    """

    _single_coord_class_name: str = "SingleBlockGenerateTest"

    class Initialize(Block):
        morphology_path: NamedPath | list[NamedPath]
        # soma: str | list[str]

    initialize: Initialize

    # def save_collection(self, circuit_entities):
    #     SaveCircuitCollectionEntity(circuits=circuit_entities)
        


import traceback
import neurom
import numpy as np
class SingleBlockGenerateTest(SingleBlockGenerateTestForm, SingleCoordinateMixin):
    
    def run(self):

        try:

            # print(f"Metrics for morphology '{self.initialize.morphology_path}'")
            
            with open(self.initialize.morphology_path, 'w') as file:
                file.write("Hello world!")

        except Exception as e:
            traceback.print_exception(e)
        
        return

    # def save_single(self):
    #     circuit_entity = SaveCircuitEntity(config_path=self.coordinate_output_root + "circuit_config.json")
    #     return circuit_entity
        
        

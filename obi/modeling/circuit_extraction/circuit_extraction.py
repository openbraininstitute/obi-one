from obi.modeling.core.form import Form
from obi.modeling.core.block import Block
from obi.modeling.core.single import SingleCoordinateMixin
from obi.modeling.core.db import SaveCircuitEntity, SaveCircuitCollectionEntity
from obi.modeling.core.base import NamedPath

class CircuitExtractions(Form):
    """
    """

    _single_coord_class_name: str = "CircuitExtraction"

    class Initialize(Block):
        circuit_path: NamedPath | list[NamedPath]
        node_set: str | list[str]

    initialize: Initialize

    def save_collection(self, circuit_entities):
        SaveCircuitCollectionEntity(circuits=circuit_entities)
        


import os
from brainbuilder.utils.sonata import split_population
from importlib.metadata import version



class CircuitExtraction(CircuitExtractions, SingleCoordinateMixin):
    """"""
    pass

    def run(self) -> str:

        try:
            print(self.coordinate_output_root)
            split_population.split_subcircuit(self.coordinate_output_root,
                                            self.initialize.node_set,
                                            self.initialize.circuit_path.path,
                                            True,
                                            False)
        except Exception as e:
            if str(e) == "Unable to synchronously create group (name already exists)":
                print("Error:", f"Subcircuit {self.initialize.node_set} already exists. Subcircuit must be deleted before running the extraction.")
            else:
                print(f"Error: {e}")
            return

    def save_single(self):
        circuit_entity = SaveCircuitEntity(config_path=self.coordinate_output_root + "circuit_config.json")
        return circuit_entity
        
        

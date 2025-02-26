from obi.modeling.core.form import Form
from obi.modeling.core.block import Block
from obi.modeling.core.single import SingleCoordinate
from obi.modeling.core.scan import Scan

class CircuitExtractions(Form):
    """
    """

    _single_coord_class_name = "CircuitExtraction"

    class Initialize(Block):
        circuit_path: str | list[str]
        node_set: str | list[str]

    initialize: Initialize


import os
from brainbuilder.utils.sonata import split_population
from importlib.metadata import version

class CircuitExtraction(CircuitExtractions, SingleCoordinate):
    """"""
    pass

    def run(self) -> str:

        try:
            split_population.split_subcircuit(self.coordinate_output_root,
                                            self.initialize.node_set,
                                            self.initialize.circuit_path,
                                            True,
                                            False)
        except Exception as e:
            if str(e) == "Unable to synchronously create group (name already exists)":
                print("Error:", f"Subcircuit {self.initialize.node_set} already exists. Subcircuit must be deleted before running the extraction.")
                return


        
        

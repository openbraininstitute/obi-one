from pydantic import PrivateAttr

from ..core.form import Form, Block, SingleTypeMixin
from ..core.scan import Scan

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
import json
class CircuitExtraction(CircuitExtractions, SingleTypeMixin):
    """"""
    pass

    def run(self):

        subcircuit_output_path = self.initialize.output_path + self.initialize.node_set + "/"

        os.makedirs(subcircuit_output_path, exist_ok=True)

        try:
            split_population.split_subcircuit(subcircuit_output_path,
                                            self.initialize.node_set,
                                            self.initialize.circuit_path,
                                            True,
                                            False)
        except Exception as e:
            if str(e) == "Unable to synchronously create group (name already exists)":
                print("Error:", f"Subcircuit {self.initialize.node_set} already exists. Subcircuit must be deleted before running the extraction.")
                return


        model_dump = self.model_dump()
        model_dump["obi_version"] = version("obi")

        with open(os.path.join(subcircuit_output_path, "model_dump.json"), "w") as json_file:
            json.dump(model_dump, json_file, indent=4)
        

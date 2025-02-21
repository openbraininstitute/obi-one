from ..core.template import Template, SubTemplate, SingleTypeMixin
from ..core.parameter_scan import ParameterScan

class CircuitExtractionParameterScanTemplate(Template):
    """
    """

    class Initialization(SubTemplate):
        circuit_path: str | list[str]
        output_root: str | list[str]
        node_set: str | list[str]

    initialize: Initialization

    # Is this reasonable? (Is there an alternative?)
    def single_version_class(self):
        return globals()["CircuitExtraction"] 


import os
from brainbuilder.utils.sonata import split_population
from importlib.metadata import version
import json
class CircuitExtraction(CircuitExtractionParameterScanTemplate, SingleTypeMixin):
    """"""
    pass

    def run_extraction(self):

        output_path = self.initialize.output_root + self.initialize.node_set + "/"

        os.makedirs(output_path, exist_ok=True)

        try:
            split_population.split_subcircuit(output_path,
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

        with open(os.path.join(output_path, "model_dump.json"), "w") as json_file:
            json.dump(model_dump, json_file, indent=4)
        

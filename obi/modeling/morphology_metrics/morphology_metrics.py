from obi.modeling.core.form import Form
from obi.modeling.core.block import Block
from obi.modeling.core.single import SingleCoordinateMixin
# from obi.modeling.core.db import SaveCircuitEntity, SaveCircuitCollectionEntity
from obi.modeling.core.path import NamedPath

class MorphologyMetricsForm(Form):
    """
    """

    _single_coord_class_name: str = "MorphologyMetrics"

    class Initialize(Block):
        morphology_path: NamedPath | list[NamedPath]
        # soma: str | list[str]

    initialize: Initialize

    # def save_collection(self, circuit_entities):
    #     SaveCircuitCollectionEntity(circuits=circuit_entities)
        


import traceback
import neurom
import numpy as np
class MorphologyMetrics(MorphologyMetricsForm, SingleCoordinateMixin):
    """
    Code orgininally created for https://github.com/openbraininstitute/neuroagent by:
    Boris Bergsma, Nicolas Frank, Jan Krepl
    in https://github.com/openbraininstitute/neuroagent/blob/main/backend/src/neuroagent/tools/morphology_features_tool.py
    """

    @staticmethod
    def get_stats(array: list[int | float]) -> dict[str, int | np.float64]:
        """Get summary stats for the array.

        Parameters
        ----------
        array
            Array of feature's statistics of a morphology

        Returns
        -------
            Dict with length, mean, sum, standard deviation, min and max of data
        """
        return {
            "len": len(array),
            "mean": np.mean(array),
            "sum": np.sum(array),
            "std": np.std(array),
            "min": np.min(array),
            "max": np.max(array),
        }

    def run(self):

        try:

            print(f"Metrics for morphology '{self.initialize.morphology_path}'")
            
            """Get features from a morphology.

            Returns
            -------
                Dict containing feature_name: value.
            """
            # Load the morphology
            # morpho = load_morphology(morphology_content.decode(), reader=reader)
            morpho = neurom.load_morphology(self.initialize.morphology_path.path)
            
            # Inserted by JI. Not used.
            # neuron = nm.load_neuron('path/to/your/morphology_file.swc')

            # Compute soma radius and soma surface area
            features = {
                "soma_radius [µm]": neurom.get("soma_radius", morpho),
                "soma_surface_area [µm^2]": neurom.get("soma_surface_area", morpho),
            }

            # Prepare a list of features that have a unique value (no statistics)
            f1 = [
                ("number_of_neurites", "Number of neurites"),
                ("number_of_sections", "Number of sections"),
                ("number_of_sections_per_neurite", "Number of sections per neurite"),
            ]

            # For each neurite type, compute the above features
            for neurite_type in neurom.NEURITE_TYPES:
                for get_name, name in f1:
                    features[f"{name} ({neurite_type.name})"] = neurom.get(
                        get_name, morpho, neurite_type=neurite_type
                    )

            # Prepare a list of features that are defined by statistics
            f2 = [
                ("section_lengths", "Section lengths [µm]"),
                ("segment_lengths", "Segment lengths [µm]"),
                ("section_radial_distances", "Section radial distance [µm]"),
                ("section_path_distances", "Section path distance [µm]"),
                ("local_bifurcation_angles", "Local bifurcation angles [˚]"),
                ("remote_bifurcation_angles", "Remote bifurcation angles [˚]"),
            ]

            # For each neurite, compute the feature values and return their statistics
            for neurite_type in neurom.NEURITE_TYPES:
                for get_name, name in f2:
                    try:
                        array = neurom.get(get_name, morpho, neurite_type=neurite_type)
                        if len(array) == 0:
                            continue
                        features[f"{name} ({neurite_type.name})"] = self.get_stats(array)
                    except (IndexError, ValueError):
                        continue


            print(features)
            # return features

            print("Metrics calculated")

        except Exception as e:
            if str(e) == "MorphologyError1":
                print("Error:", e)
            else:
                traceback.print_exception(e)
            return

    # def save_single(self):
    #     circuit_entity = SaveCircuitEntity(config_path=self.coordinate_output_root + "circuit_config.json")
    #     return circuit_entity
        
        

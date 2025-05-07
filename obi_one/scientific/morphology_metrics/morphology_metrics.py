from typing import Union, ClassVar, Annotated
from pydantic import BaseModel, Field

from obi_one.core.form import Form
from obi_one.core.block import Block
from obi_one.core.single import SingleCoordinateMixin
from obi_one.core.path import NamedPath
from obi_one.core.base import OBIBaseModel
from obi_one.database.db_classes import ReconstructionMorphologyFromID

from fastapi import HTTPException


class MorphologyMetricsForm(Form):
    """
    """

    single_coord_class_name: ClassVar[str] = "MorphologyMetrics"
    name: ClassVar[str] = "1. Morphology metrics example name"
    description: ClassVar[str] = "2. Morphology metrics example description"

    class Initialize(Block):
        morphology: ReconstructionMorphologyFromID | list[ReconstructionMorphologyFromID] = Field(description="3. Morphology description")

    initialize: Initialize

    def save(self, circuit_entities):
        """
        Add entitysdk calls to save the collection
        """
        pass


class MorphologyMetricsOutput(BaseModel):

        aspect_ratio: Annotated[float, Field(title="aspect_ratio", description="Calculates the min/max ratio of the principal direction extents along the plane.")]
        circularity: Annotated[float, Field(title="circularity", description="Calculates the circularity of the morphology points along the plane.")]
        length_fraction_above_soma: Annotated[float, Field(title="length_fraction_above_soma", description="Returns the length fraction of the segments that have their midpoints higher than the soma.")]
        max_radial_distance: Annotated[float, Field(title="max_radial_distance", description="Get the maximum radial distances of the termination sections.")]
        number_of_neurites: Annotated[int, Field(title="number_of_neurites", description="Number of neurites in a morph.")]

        soma_radius: Annotated[float, Field(title="soma_radius [µm]", description="The radius of the soma in micrometers.")]
        soma_surface_area: Annotated[float, Field(title="soma_surface_area [µm^2]", description="The surface area of the soma in square micrometers.")]


        @classmethod
        def from_morphology(cls, neurom_morphology):
            import neurom
            return cls(
                aspect_ratio=neurom.get("aspect_ratio", neurom_morphology),
                circularity=neurom.get("circularity", neurom_morphology),
                length_fraction_above_soma=neurom.get("length_fraction_above_soma", neurom_morphology),
                max_radial_distance=neurom.get("max_radial_distance", neurom_morphology),
                number_of_neurites=neurom.get("number_of_neurites", neurom_morphology),
                soma_radius=neurom.get("soma_radius", neurom_morphology),
                soma_surface_area=neurom.get("soma_surface_area", neurom_morphology),
            )
            


import traceback
import neurom
import numpy as np
class MorphologyMetrics(MorphologyMetricsForm, SingleCoordinateMixin):

    def run(self):
        
        try:
            self.morphology_metrics = MorphologyMetricsOutput.from_morphology(self.initialize.morphology.neurom_morphology)

        except Exception as e:  # noqa: BLE001
            print(f"An error occurred: {e}")
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")
            

    # def data(self) -> MorphologyMetricsOutput:
    #     """
    #     Return the data to the client
    #     """
    #     return MorphologyMetricsOutput.from_morphology(self.initialize.morphology.neurom_morphology)








# """
#     Code orgininally created for https://github.com/openbraininstitute/neuroagent by:
#     Boris Bergsma, Nicolas Frank, Jan Krepl
#     in https://github.com/openbraininstitute/neuroagent/blob/main/backend/src/neuroagent/tools/morphology_features_tool.py
#     """

#     @staticmethod
#     def get_stats(array: list[int | float]) -> dict[str, int | np.float64]:
#         """Get summary stats for the array.

#         Parameters
#         ----------
#         array
#             Array of feature's statistics of a morphology

#         Returns
#         -------
#             Dict with length, mean, sum, standard deviation, min and max of data
#         """
#         return {
#             "len": len(array),
#             "mean": np.mean(array),
#             "sum": np.sum(array),
#             "std": np.std(array),
#             "min": np.min(array),
#             "max": np.max(array),
#         }

#     def run(self):

#         try:

#             print(f"Metrics for morphology '{self.initialize.morphology_path}'")
            
#             """Get features from a morphology.

#             Returns
#             -------
#                 Dict containing feature_name: value.
#             """
#             # Load the morphology
#             # morpho = load_morphology(morphology_content.decode(), reader=reader)
#             morpho = neurom.load_morphology(self.initialize.morphology_path.path)
            
#             # Inserted by JI. Not used.
#             # neuron = nm.load_neuron('path/to/your/morphology_file.swc')

#             # Compute soma radius and soma surface area
#             features = {
#                 "soma_radius [µm]": neurom.get("soma_radius", morpho),
#                 "soma_surface_area [µm^2]": neurom.get("soma_surface_area", morpho),
#             }

#             # Prepare a list of features that have a unique value (no statistics)
#             f1 = [
#                 ("number_of_neurites", "Number of neurites"),
#                 ("number_of_sections", "Number of sections"),
#                 ("number_of_sections_per_neurite", "Number of sections per neurite"),
#             ]

#             # For each neurite type, compute the above features
#             for neurite_type in neurom.NEURITE_TYPES:
#                 for get_name, name in f1:
#                     features[f"{name} ({neurite_type.name})"] = neurom.get(
#                         get_name, morpho, neurite_type=neurite_type
#                     )

#             # Prepare a list of features that are defined by statistics
#             f2 = [
#                 ("section_lengths", "Section lengths [µm]"),
#                 ("segment_lengths", "Segment lengths [µm]"),
#                 ("section_radial_distances", "Section radial distance [µm]"),
#                 ("section_path_distances", "Section path distance [µm]"),
#                 ("local_bifurcation_angles", "Local bifurcation angles [˚]"),
#                 ("remote_bifurcation_angles", "Remote bifurcation angles [˚]"),
#             ]

#             # For each neurite, compute the feature values and return their statistics
#             for neurite_type in neurom.NEURITE_TYPES:
#                 for get_name, name in f2:
#                     try:
#                         array = neurom.get(get_name, morpho, neurite_type=neurite_type)
#                         if len(array) == 0:
#                             continue
#                         features[f"{name} ({neurite_type.name})"] = self.get_stats(array)
#                     except (IndexError, ValueError):
#                         continue


#             print(features)
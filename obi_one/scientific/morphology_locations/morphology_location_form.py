from typing import Union, ClassVar, Annotated
from pydantic import BaseModel, Field
from neurom.core.types import SectionType

from obi_one.core.form import Form
from obi_one.core.block import Block
from obi_one.core.single import SingleCoordinateMixin
from obi_one.database.db_classes import ReconstructionMorphologyFromID

from fastapi import HTTPException
from pathlib import Path

class MorphologyLocationsForm(Form):
    """
    """

    single_coord_class_name: ClassVar[str] = "MorphologyLocations"
    name: ClassVar[str] = "Point locations on neurite skeletons"
    description: ClassVar[str] = "Generates optionally clustered locations on neurites of a morphology skeleton"

    class Initialize(Block):
        morphology: ReconstructionMorphologyFromID | list[ReconstructionMorphologyFromID] | Path | list[Path]
        n_centers: int | list[int]
        n_per_center: int | list[int]
        srcs_per_center: int | list[int]
        center_pd_mean: float | list[float]
        center_pd_sd: float | list[float]
        max_dist_from_center: float | list[float]
        lst_section_types: list[int] | list[list[int]]

    initialize: Initialize

    def save(self, circuit_entities):
        """
        Add entitysdk calls to save the collection
        """
        pass


class MorphologyLocations(MorphologyLocationsForm,SingleCoordinateMixin):
    """
    """

    def run(self):
        
        try:
            from .specified_morphology_locations import generate_neurite_locations_on
            if isinstance(self.initialize.morphology, Path):
                import morphio
                m = morphio.Morphology(self.initialize.morphology)
            else:
                m = self.initialize.morphology.morphio_morphology

            df = generate_neurite_locations_on(
                m,
                self.initialize.n_centers,
                self.initialize.n_per_center,
                self.initialize.srcs_per_center,
                self.initialize.center_pd_mean,
                self.initialize.center_pd_sd,
                self.initialize.max_dist_from_center,
                self.initialize.lst_section_types
            )
            print(df)

        except Exception as e:  # noqa: BLE001
            print(f"An error occurred: {e}")
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")
            
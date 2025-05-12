import numpy
import pandas
import os

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
        max_dist_from_center: Union[float, None] | list[Union[float, None]]
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

    def _generate_plot(self, m, df):
        import neurom.view
        import neurom.io
        
        from matplotlib import pyplot as plt
        from .specified_morphology_locations import _SEC_ID, _SEG_ID, _SEG_OFF, _PRE_IDX

        def location_xyz(row):
            secid = int(row[_SEC_ID])
            segid = int(row[_SEG_ID])
            o = row[_SEG_OFF]
            seg = m.sections[secid - 1].points[segid:(segid + 2)]
            dseg = numpy.diff(seg, axis=0)[0]
            dseg = dseg / numpy.linalg.norm(dseg)
            return pandas.Series(seg[0] + o * dseg,
                                index=["x", "y", "z"])


        fig = plt.figure(figsize=(3, 6))
        ax = fig.gca()

        xyz = pandas.concat([df.apply(location_xyz, axis=1), df[_PRE_IDX]], axis=1)
        neurom.view.plot_morph(neurom.io.utils.Morphology(m), ax=ax)
        xyz.groupby(_PRE_IDX).apply(lambda _x: ax.scatter(_x["x"], _x["y"], s=6))
        plt.axis("equal")
        return fig


    def run(self):
        
        try:
            print(self.coordinate_output_root)
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
            
            fig = self._generate_plot(m, df)
            fig.savefig(os.path.join(self.coordinate_output_root, "locations_plot.pdf"))
            df.to_csv(os.path.join(self.coordinate_output_root, "morphology_locations.csv"))

        except Exception as e:  # noqa: BLE001
            print(f"An error occurred: {e}")
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")
            
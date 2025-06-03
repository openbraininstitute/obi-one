import logging
from pathlib import Path
from typing import ClassVar

import morphio
import neurom.io
import neurom.view
import numpy as np
import pandas as pd
from fastapi import HTTPException
from matplotlib import pyplot as plt
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.form import Form
from obi_one.core.single import SingleCoordinateMixin
from obi_one.database.reconstruction_morphology_from_id import ReconstructionMorphologyFromID
from obi_one.scientific.unions.unions_morphology_locations import MorphologyLocationUnion

from .specified_morphology_locations import _PRE_IDX, _SEC_ID, _SEG_ID, _SEG_OFF

L = logging.getLogger(__name__)


class MorphologyLocationsForm(Form):
    """Form for generating locations on a morphology skeleton."""

    single_coord_class_name: ClassVar[str] = "MorphologyLocations"
    name: ClassVar[str] = "Point locations on neurite skeletons"
    description: ClassVar[str] = (
        "Generates optionally clustered locations on neurites of a morphology skeleton"
    )

    class Initialize(Block):
        morphology: (
            ReconstructionMorphologyFromID
            | list[ReconstructionMorphologyFromID]
            | Path
            | list[Path]
        ) = Field(title="Morphology", description="The morphology skeleton to place locations on")

    initialize: Initialize
    morph_locations: MorphologyLocationUnion = Field(
        title="Morphology locations",
        description="Parameterization of locations on the neurites of the morphology",
    )


class MorphologyLocations(MorphologyLocationsForm, SingleCoordinateMixin):
    """Generates locations on a morphology skeleton."""

    @staticmethod
    def generate_plot(m: morphio.Morphology, dataframe: pd.DataFrame) -> plt.figure:
        """Generate a plot of the morphology with locations on it."""

        def location_xyz(row: pd.Series) -> plt.figure:
            secid = int(row[_SEC_ID])
            segid = int(row[_SEG_ID])
            o = row[_SEG_OFF]
            seg = m.sections[secid - 1].points[segid : (segid + 2)]
            dseg = np.diff(seg, axis=0)[0]
            dseg = dseg / np.linalg.norm(dseg)
            return pd.Series(seg[0] + o * dseg, index=["x", "y", "z"])

        fig = plt.figure(figsize=(3, 6))
        ax = fig.gca()

        xyz = pd.concat([dataframe.apply(location_xyz, axis=1), dataframe[_PRE_IDX]], axis=1)
        neurom.view.plot_morph(neurom.io.utils.Morphology(m), ax=ax)
        xyz.groupby(_PRE_IDX).apply(lambda _x: ax.scatter(_x["x"], _x["y"], s=6))
        plt.axis("equal")
        return fig

    def run(self) -> None:
        try:
            if isinstance(self.initialize.morphology, Path):
                m = morphio.Morphology(self.initialize.morphology)
            else:
                m = self.initialize.morphology.morphio_morphology
            dataframe = self.morph_locations.points_on(m)

            fig = MorphologyLocations.generate_plot(m, dataframe)
            fig.savefig(self.coordinate_output_root / "locations_plot.pdf")
            dataframe.to_csv(self.coordinate_output_root / "morphology_locations.csv")

        except Exception as e:
            L.error(f"An error occurred: {e}")
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}") from e

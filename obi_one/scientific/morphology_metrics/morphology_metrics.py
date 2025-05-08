from typing import Annotated, ClassVar

from fastapi import HTTPException
from pydantic import BaseModel, Field

from obi_one.core.block import Block
from obi_one.core.form import Form
from obi_one.core.single import SingleCoordinateMixin
from obi_one.database.db_classes import ReconstructionMorphologyFromID


class MorphologyMetricsForm(Form):
    """ """

    single_coord_class_name: ClassVar[str] = "MorphologyMetrics"
    name: ClassVar[str] = "Morphology Metrics"
    description: ClassVar[str] = "Calculates morphology metrics for a given morphologies."

    class Initialize(Block):
        morphology: ReconstructionMorphologyFromID | list[ReconstructionMorphologyFromID] = Field(
            description="3. Morphology description"
        )

    initialize: Initialize

    def save(self, circuit_entities):
        """Add entitysdk calls to save the collection"""


class MorphologyMetricsOutput(BaseModel):
    aspect_ratio: Annotated[
        float,
        Field(
            title="aspect_ratio",
            description="Calculates the min/max ratio of the principal direction extents along the plane.",
        ),
    ]
    circularity: Annotated[
        float,
        Field(
            title="circularity",
            description="Calculates the circularity of the morphology points along the plane.",
        ),
    ]
    length_fraction_above_soma: Annotated[
        float,
        Field(
            title="length_fraction_above_soma",
            description="Returns the length fraction of the segments that have their midpoints higher than the soma.",
        ),
    ]
    max_radial_distance: Annotated[
        float,
        Field(
            title="max_radial_distance",
            description="Get the maximum radial distances of the termination sections.",
        ),
    ]
    number_of_neurites: Annotated[
        int, Field(title="number_of_neurites", description="Number of neurites in a morph.")
    ]

    soma_radius: Annotated[
        float, Field(title="soma_radius [µm]", description="The radius of the soma in micrometers.")
    ]
    soma_surface_area: Annotated[
        float,
        Field(
            title="soma_surface_area [µm^2]",
            description="The surface area of the soma in square micrometers.",
        ),
    ]

    @classmethod
    def from_morphology(cls, neurom_morphology):
        return cls(
            aspect_ratio=neurom.get("aspect_ratio", neurom_morphology),
            circularity=neurom.get("circularity", neurom_morphology),
            length_fraction_above_soma=neurom.get("length_fraction_above_soma", neurom_morphology),
            max_radial_distance=neurom.get("max_radial_distance", neurom_morphology),
            number_of_neurites=neurom.get("number_of_neurites", neurom_morphology),
            soma_radius=neurom.get("soma_radius", neurom_morphology),
            soma_surface_area=neurom.get("soma_surface_area", neurom_morphology),
        )


import neurom


class MorphologyMetrics(MorphologyMetricsForm, SingleCoordinateMixin):
    def run(self):
        try:
            print(
                MorphologyMetricsOutput.from_morphology(
                    self.initialize.morphology.neurom_morphology
                )
            )

        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

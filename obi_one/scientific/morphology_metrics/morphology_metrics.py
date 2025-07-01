import io
import logging
from typing import Annotated, ClassVar

L = logging.getLogger(__name__)

import entitysdk
import neurom
from entitysdk.models.morphology import ReconstructionMorphology
from fastapi import HTTPException
from neurom import load_morphology
from pydantic import BaseModel, Field

from obi_one.core.block import Block
from obi_one.core.form import Form
from obi_one.core.single import SingleCoordinateMixin
from obi_one.database.reconstruction_morphology_from_id import ReconstructionMorphologyFromID


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
        """Add entitysdk calls to save the collection."""


class MorphologyMetricsOutput(BaseModel):
    aspect_ratio: Annotated[
        float,
        Field(
            title="aspect_ratio",
            description="Calculates the min/max ratio of the principal direction extents \
                along the plane.",
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
            description="Returns the length fraction of the segments that have their midpoints \
                            higher than the soma.",
        ),
    ]
    max_radial_distance: Annotated[
        float,
        Field(
            title="max_radial_distance",
            description="The maximum radial distance from the soma in micrometers.",
        ),
    ]
    number_of_neurites: Annotated[
        int, Field(title="number_of_neurites", description="Number of neurites in a morphology.")
    ]

    soma_radius: Annotated[
        float, Field(title="soma_radius [μm]", description="The radius of the soma in micrometers.")
    ]
    soma_surface_area: Annotated[
        float,
        Field(
            title="soma_surface_area [μm^2]",
            description="The surface area of the soma in square micrometers.",
        ),
    ]
    total_length: Annotated[
        float,
        Field(
            title="total_length [μm]",
            description="The total length of the morphology neurites in micrometers.",
        ),
    ]
    total_height: Annotated[
        float,
        Field(
            title="total_height [μm]",
            description="The total height (Y-range) of the morphology in micrometers.",
        ),
    ]
    total_height: Annotated[
        float,
        Field(
            title="total_width [μm]",
            description="The total width (X-range) of the morphology in micrometers.",
        ),
    ]
    total_depth: Annotated[
        float,
        Field(
            title="total_depth [μm]",
            description="The total depth (Z-range) of the morphology in micrometers.",
        ),
    ]
    total_area: Annotated[
        float,
        Field(
            title="total_area [μm^2]",
            description="The total surface area of all sections in square micrometers.",
        ),
    ]
    total_volume: Annotated[
        float,
        Field(
            title="total_volume [μm^3]",
            description="The total volume of all sections in cubic micrometers.",
        ),
    ]
    section_lengths: Annotated[
        list[float],
        Field(
            title="section_lengths [μm]",
            description="The distribution of lengths per section in micrometers.",
        ),
    ]
    segment_radii: Annotated[
        list[float],
        Field(
            title="segment_radii [μm]",
            description="The distribution of radii of the morphology in micrometers.",
        ),
    ]
    number_of_sections: Annotated[
        float,
        Field(
            title="number_of_sections",
            description="The number of sections in the morphology.",
        ),
    ]
    local_bifurcation_angles: Annotated[
        list[float],
        Field(
            title="local_bifurcation_angles [rad]",
            description="Angles between two sections computed at the bifurcation (local).",
        ),
    ]
    remote_bifurcation_angles: Annotated[
        list[float],
        Field(
            title="remote_bifurcation_angles [rad]",
            description="Angles between two sections computed at the end of the sections (remote).",
        ),
    ]
    section_path_distances: Annotated[
        list[float],
        Field(
            title="section_path_distances [μm]",
            description="Path distances from the soma to section endpoints in micrometers.",
        ),
    ]
    section_radial_distances: Annotated[
        list[float],
        Field(
            title="section_radial_distances [μm]",
            description="Radial distance from the soma to section endpoints in micrometers.",
        ),
    ]
    section_branch_orders: Annotated[
        list[float],
        Field(
            title="section_branch_orders",
            description="The distribution of branch orders of sections, computed from soma.",
        ),
    ]
    section_strahler_orders: Annotated[
        list[float],
        Field(
            title="section_strahler_orders",
            description="The distribution of strahler branch orders of sections, computed from terminals.",
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
            total_length=neurom.get("total_length", neurom_morphology),
            total_height=neurom.get("total_height", neurom_morphology),
            total_width=neurom.get("total_width", neurom_morphology),
            total_depth=neurom.get("total_depth", neurom_morphology),
            total_area=neurom.get("total_area", neurom_morphology),
            total_volume=neurom.get("total_volume", neurom_morphology),
            section_lengths=neurom.get("section_lengths", neurom_morphology),
            segment_radii=neurom.get("segment_radii", neurom_morphology),
            number_of_sections=neurom.get("number_of_sections", neurom_morphology),
            local_bifurcation_angles=neurom.get("local_bifurcation_angles", neurom_morphology),
            remote_bifurcation_angles=neurom.get("remote_bifurcation_angles", neurom_morphology),
            section_path_distances=neurom.get("section_path_distances", neurom_morphology),
            section_radial_distances=neurom.get("section_radial_distances", neurom_morphology),
            section_branch_orders=neurom.get("section_branch_orders", neurom_morphology),
            section_strahler_orders=neurom.get("section_strahler_orders", neurom_morphology),
        )



class MorphologyMetrics(MorphologyMetricsForm, SingleCoordinateMixin):
    def run(self, db_client: entitysdk.client.Client = None):
        try:
            print("Running Morphology Metrics...")
            morphology_metrics = MorphologyMetricsOutput.from_morphology(
                    self.initialize.morphology.neurom_morphology(db_client=db_client)
                )
            L.info(morphology_metrics)

            return morphology_metrics

        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")


def get_morphology_metrics(
                reconstruction_morphology_id: str, 
                db_client: entitysdk.client.Client
            ) -> MorphologyMetricsOutput:

    morphology = db_client.get_entity(
        entity_id=reconstruction_morphology_id, 
        entity_type=ReconstructionMorphology
    )

    # Iterate through the assets of the morphology to find the one with content
    # type "application/asc"
    for asset in morphology.assets:
        if asset.content_type == "application/swc":
            # Download the content into memory
            content = db_client.download_content(
                entity_id=morphology.id,
                entity_type=ReconstructionMorphology,
                asset_id=asset.id,
            ).decode(encoding="utf-8")

            # Use StringIO to create a file-like object in memory from the string content
            neurom_morphology = load_morphology(io.StringIO(content), reader="swc")

            # Calculate the metrics using neurom
            morphology_metrics = MorphologyMetricsOutput.from_morphology(neurom_morphology)

            return morphology_metrics
    return None

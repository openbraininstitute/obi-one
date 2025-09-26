import io
import logging
from typing import Annotated, Self

import entitysdk
import neurom
from entitysdk.models.cell_morphology import CellMorphology
from neurom import load_morphology
from pydantic import BaseModel, Field

L = logging.getLogger(__name__)

MORPHOLOGY_METRICS = [
    "aspect_ratio",
    "circularity",
    "length_fraction_above_soma",
    "max_radial_distance",
    "number_of_neurites",
    "soma_radius",
    "soma_surface_area",
    "total_length",
    "total_height",
    "total_width",
    "total_depth",
    "total_area",
    "total_volume",
    "section_lengths",
    "segment_radii",
    "number_of_sections",
    "local_bifurcation_angles",
    "remote_bifurcation_angles",
    "section_path_distances",
    "section_radial_distances",
    "section_branch_orders",
    "section_strahler_orders",
]


class MorphologyMetricsOutput(BaseModel):
    aspect_ratio: Annotated[
        float | None,
        Field(
            title="aspect_ratio",
            description="Calculates the min/max ratio of the principal direction extents \
                along the plane.",
            default=None,
        ),
    ]
    circularity: Annotated[
        float | None,
        Field(
            title="circularity",
            description="Calculates the circularity of the morphology points along the plane.",
            default=None,
        ),
    ]
    length_fraction_above_soma: Annotated[
        float | None,
        Field(
            title="length_fraction_above_soma",
            description="Returns the length fraction of the segments that have their midpoints \
                            higher than the soma.",
            default=None,
        ),
    ]
    max_radial_distance: Annotated[
        float | None,
        Field(
            title="max_radial_distance",
            description="The maximum radial distance from the soma in micrometers.",
            default=None,
        ),
    ]
    number_of_neurites: Annotated[
        int | None,
        Field(
            title="number_of_neurites",
            description="Number of neurites in a morphology.",
            default=None,
        ),
    ]

    soma_radius: Annotated[
        float | None,
        Field(
            title="soma_radius [μm]",
            description="The radius of the soma in micrometers.",
            default=None,
        ),
    ]
    soma_surface_area: Annotated[
        float | None,
        Field(
            title="soma_surface_area [μm^2]",
            description="The surface area of the soma in square micrometers.",
            default=None,
        ),
    ]
    total_length: Annotated[
        float | None,
        Field(
            title="total_length [μm]",
            description="The total length of the morphology neurites in micrometers.",
            default=None,
        ),
    ]
    total_height: Annotated[
        float | None,
        Field(
            title="total_height [μm]",
            description="The total height (Y-range) of the morphology in micrometers.",
            default=None,
        ),
    ]
    total_height: Annotated[
        float | None,
        Field(
            title="total_width [μm]",
            description="The total width (X-range) of the morphology in micrometers.",
            default=None,
        ),
    ]
    total_depth: Annotated[
        float | None,
        Field(
            title="total_depth [μm]",
            description="The total depth (Z-range) of the morphology in micrometers.",
            default=None,
        ),
    ]
    total_area: Annotated[
        float | None,
        Field(
            title="total_area [μm^2]",
            description="The total surface area of all sections in square micrometers.",
            default=None,
        ),
    ]
    total_volume: Annotated[
        float | None,
        Field(
            title="total_volume [μm^3]",
            description="The total volume of all sections in cubic micrometers.",
            default=None,
        ),
    ]
    section_lengths: Annotated[
        list[float] | None,
        Field(
            title="section_lengths [μm]",
            description="The distribution of lengths per section in micrometers.",
            default=None,
        ),
    ]
    segment_radii: Annotated[
        list[float] | None,
        Field(
            title="segment_radii [μm]",
            description="The distribution of radii of the morphology in micrometers.",
            default=None,
        ),
    ]
    number_of_sections: Annotated[
        float | None,
        Field(
            title="number_of_sections",
            description="The number of sections in the morphology.",
            default=None,
        ),
    ]
    local_bifurcation_angles: Annotated[
        list[float] | None,
        Field(
            title="local_bifurcation_angles [rad]",
            description="Angles between two sections computed at the bifurcation (local).",
            default=None,
        ),
    ]
    remote_bifurcation_angles: Annotated[
        list[float] | None,
        Field(
            title="remote_bifurcation_angles [rad]",
            description="Angles between two sections computed at the end of the sections (remote).",
            default=None,
        ),
    ]
    section_path_distances: Annotated[
        list[float] | None,
        Field(
            title="section_path_distances [μm]",
            description="Path distances from the soma to section endpoints in micrometers.",
            default=None,
        ),
    ]
    section_radial_distances: Annotated[
        list[float] | None,
        Field(
            title="section_radial_distances [μm]",
            description="Radial distance from the soma to section endpoints in micrometers.",
            default=None,
        ),
    ]
    section_branch_orders: Annotated[
        list[float] | None,
        Field(
            title="section_branch_orders",
            description="The distribution of branch orders of sections, computed from soma.",
            default=None,
        ),
    ]
    section_strahler_orders: Annotated[
        list[float] | None,
        Field(
            title="section_strahler_orders",
            description="The distribution of strahler branch orders of sections, computed from \
                terminals.",
            default=None,
        ),
    ]

    @classmethod
    def from_morphology(cls, neurom_morphology: neurom.core.Morphology) -> Self:
        values = {metric: neurom.get(metric, neurom_morphology) for metric in MORPHOLOGY_METRICS}
        return cls(**values)


def get_morphology_metrics(
    cell_morphology_id: str,
    db_client: entitysdk.client.Client,
    requested_metrics: list[str] | None = None,
) -> MorphologyMetricsOutput:
    morphology = db_client.get_entity(entity_id=cell_morphology_id, entity_type=CellMorphology)

    for asset in morphology.assets:
        if asset.content_type == "application/swc":
            content = db_client.download_content(
                entity_id=morphology.id,
                entity_type=CellMorphology,
                asset_id=asset.id,
            ).decode(encoding="utf-8")

            neurom_morphology = load_morphology(io.StringIO(content), reader="swc")

            if requested_metrics:
                values = {
                    metric: neurom.get(metric, neurom_morphology) for metric in requested_metrics
                }
                return MorphologyMetricsOutput(**values)
            return MorphologyMetricsOutput.from_morphology(neurom_morphology)
    return None

from pydantic import BaseModel, Field


class MorphologyLocation(BaseModel):
    """One generated location on a morphology."""

    section_id: int = Field(
        ge=0,
        description=(
            "SONATA global section id: 0 for the soma, then neurites in NEURON section order. "
            "Matches the `sonata_section_id` the viewer receives for each rendered section."
        ),
    )
    offset: float = Field(
        ge=0.0,
        le=1.0,
        description="Normalized position along the section: 0.0 is its start, 1.0 its end.",
    )


class MorphologyLocationsPreview(BaseModel):
    """The locations a morphology-location block generates on one morphology.

    `section_id` and `offset` are the same values the block writes to `compartment_sets.json`
    when the workflow runs. The node id of each persisted row is not included: it comes from the
    neuron set the block is applied to, which a single-morphology preview does not have.
    """

    locations: list[MorphologyLocation]

import abc
from typing import Self

import morphio
import pandas  # noqa: ICN001
from pydantic import Field, model_validator

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement


class MorphologyLocationsBlock(Block, abc.ABC):
    """Base class representing parameterized locations on morphology skeletons."""

    random_seed: int | list[int] = Field(
        default=0,
        title="Random Seed",
        description="Seed for the random generation of locations.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    number_of_locations: int | list[int] = Field(
        default=1,
        title="Number of Locations",
        description="Number of locations to generate on morphology.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    section_types: int | list[int] = Field(
        default=1,
        ge=0,
        title="Section Types",
        description=(
            "SWC section types to generate locations on. "
            "0: undefined, 1: soma, 2: axon, 3: basal dendrite, "
            "4: apical dendrite, 5+: custom."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    @abc.abstractmethod
    def _make_points(self, morphology: morphio.Morphology) -> pandas.DataFrame:
        """Returns a generated list of points for the morphology."""

    @abc.abstractmethod
    def _check_parameter_values(self) -> None:
        """Do specific checks on the validity of parameters."""

    @model_validator(mode="after")
    def check_parameter_values(self) -> Self:
        # Only check whenever list are resolved to individual objects
        self._check_parameter_values()
        return self

    def points_on(self, morphology: morphio.Morphology) -> pandas.DataFrame:
        self.enforce_no_multi_param()
        return self._make_points(morphology)

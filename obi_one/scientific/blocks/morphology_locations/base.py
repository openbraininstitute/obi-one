import abc
from typing import Self

import morphio
import pandas  # noqa: ICN001
from pydantic import Field, model_validator

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.library.entity_property_types import (
    MappedPropertiesGroup,
    MorphologySourceMappedProperties,
)


class MorphologyLocationsBlock(Block, abc.ABC):
    """Base class representing parameterized locations on morphology skeletons."""

    random_seed: int | list[int] = Field(
        default=0,
        title="Random seed",
        description="Seed for the random generation of locations",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    number_of_locations: int | list[int] = Field(
        default=1,
        title="Number of locations",
        description="Number of locations to generate on morphology",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    section_types: tuple[int, ...] | list[tuple[int, ...]] | None = Field(
        default=None,
        title="Section types",
        description="Choose which morphology sections can receive generated locations.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.MORPHOLOGY_SECTION_TYPE_SELECTION,
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.MORPHOLOGY_SOURCE,
            SchemaKey.PROPERTY: MorphologySourceMappedProperties.SECTION_TYPES,
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

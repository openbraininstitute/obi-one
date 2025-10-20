import abc
from typing import Self

import morphio
import pandas  # noqa: ICN001
from pydantic import Field, model_validator

from obi_one.core.block import Block


class MorphologyLocationsBlock(Block, abc.ABC):
    """Base class representing parameterized locations on morphology skeletons."""

    random_seed: int | list[int] = Field(
        default=0, name="Random seed", description="Seed for the random generation of locations"
    )
    number_of_locations: int | list[int] = Field(
        default=1,
        name="Number of locations",
        description="Number of locations to generate on morphology",
    )
    section_types: tuple[int, ...] | list[tuple[int, ...]] | None = Field(
        default=None,
        name="Section types",
        description="Types of sections to generate locations on. 2: axon, 3: basal, 4: apical",
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

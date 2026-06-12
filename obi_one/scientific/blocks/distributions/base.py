import abc

import numpy as np
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement


class Distribution(Block, abc.ABC):
    """Distribution base class."""

    min: float | list[float] | None = Field(
        default=None,
        title="Minimum",
        description="Minimum value below which we truncate.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )
    max: float | list[float] | None = Field(
        default=None,
        title="Maximum",
        description="Maximum value above which we truncate.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )
    include_min: bool = Field(
        default=True,
        title="Include minimum",
        description="Include minimum value (if specified).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )
    include_max: bool = Field(
        default=False,
        title="Include maximum",
        description="Include maximum value (if specified).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )

    @staticmethod
    def _check_constraints(
        ge: float | None = None,
        le: float | None = None,
        gt: float | None = None,
        lt: float | None = None,
    ) -> None:
        """Check if constraints are logically consistent."""
        if ge is not None and le is not None and ge > le:
            msg = "ge must be less than or equal to le."
            raise ValueError(msg)
        if gt is not None and lt is not None and gt >= lt:
            msg = "gt must be less than lt."
            raise ValueError(msg)
        if ge is not None and lt is not None and ge > lt:
            msg = "ge must be less than or equal to lt."
            raise ValueError(msg)
        if gt is not None and le is not None and gt >= le:
            msg = "gt must be less than le."
            raise ValueError(msg)
        if ge is not None and gt is not None:
            msg = "Only one of ge and gt can be specified."
            raise ValueError(msg)
        if le is not None and lt is not None:
            msg = "Only one of le and lt can be specified."
            raise ValueError(msg)

    def sample(
        self,
        n: int = 1,
        ge: float | None = None,
        le: float | None = None,
        gt: float | None = None,
        lt: float | None = None,
        rng: np.random.Generator | None = None,
    ) -> list[float]:
        """Sample n values from the distribution."""
        self._check_constraints(ge=ge, le=le, gt=gt, lt=lt)
        initial_samples = self._sample_generator(n, rng=rng)
        final_samples = self._apply_constraints(initial_samples, ge=ge, le=le, gt=gt, lt=lt)
        return final_samples

    def sample_with_constraints(
        self, n: int = 1, rng: np.random.Generator | None = None
    ) -> list[float]:
        kwargs = {}
        if self.include_min:
            kwargs["ge"] = self.min
        else:
            kwargs["gt"] = self.min
        if self.include_max:
            kwargs["le"] = self.max
        else:
            kwargs["lt"] = self.max
        return self.sample(n=n, rng=rng, **kwargs)

    @abc.abstractmethod
    def _sample_generator(self, n: int = 1, rng: np.random.Generator | None = None) -> list[float]:
        msg = "Subclasses must implement the _sample_generator method."
        raise NotImplementedError(msg)

    @staticmethod
    def _apply_constraints(
        samples: list[float],
        ge: float | None = None,
        le: float | None = None,
        gt: float | None = None,
        lt: float | None = None,
    ) -> list[float]:
        """Apply constraints to the samples."""
        constrained_samples = []
        for sample in samples:
            if ge is not None and sample < ge:
                constrained_samples.append(ge)
            elif gt is not None and sample <= gt:
                constrained_samples.append(
                    gt + 1e-9
                )  # Add a small epsilon to ensure it's greater than gt
            elif le is not None and sample > le:
                constrained_samples.append(le)
            elif lt is not None and sample >= lt:
                constrained_samples.append(
                    lt - 1e-9
                )  # Subtract a small epsilon to ensure it's less than lt
            else:
                constrained_samples.append(sample)
        return constrained_samples

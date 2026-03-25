import abc
from typing import Never

from obi_one.core.block import Block


class Distribution(Block, abc.ABC):
    """Distribution."""

    def _check_constraints(
        self,
        ge: float | None = None,
        le: float | None = None,
        gt: float | None = None,
        lt: float | None = None,
    ) -> bool:
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

    @abc.abstractmethod
    def sample(
        self,
        n: int = 1,
        ge: float | None = None,
        le: float | None = None,
        gt: float | None = None,
        lt: float | None = None,
    ) -> Never:
        """Sample n values from the distribution."""
        self._check_constraints(ge=ge, le=le, gt=gt, lt=lt)
        self._sample_generator(n)
        self._apply_constraints(n=n, ge=ge, le=le, gt=gt, lt=lt)

    def _sample_generator(self, n: int = 1) -> Never:
        msg = "Subclasses must implement the _sample_generator method."
        raise NotImplementedError(msg)

    def _apply_constraints(
        self,
        n: int = 1,
        ge: float | None = None,
        le: float | None = None,
        gt: float | None = None,
        lt: float | None = None,
    ) -> list[float]:
        """Apply constraints to the samples."""
        msg = "Subclasses must implement the _apply_constraints method."
        raise NotImplementedError(msg)

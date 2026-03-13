import abc
from typing import Never

from obi_one.core.block import Block


class Distribution(Block, abc.ABC):
    """Distribution."""

    @abc.abstractmethod
    def sample(self, n: int = 1) -> Never:
        """Sample n values from the distribution."""
        msg = "Subclasses must implement the sample_n method."
        raise NotImplementedError(msg)

from abc import ABC, abstractmethod
from collections.abc import Iterator

from pydantic import Field, NonNegativeFloat

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.library.generate_simulations.helpers import (
    resolved_sonata_delay_duration_dict,
)


class Timestamps(Block, ABC):
    start_time: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.0,
        description="Sart time of the timestamps in milliseconds (ms).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    def timestamps(self) -> list:
        return self._resolve_timestamps()

    @abstractmethod
    def _resolve_timestamps(self) -> list:
        pass

    def enumerate_zero_checked_timestamp_stimulus_dicts(
        self, timestamp_offset: float, duration: NonNegativeFloat
    ) -> Iterator[tuple[int, NonNegativeFloat, dict]]:
        """Enumerate timestamps with their resolved SONATA delay/duration dicts.

        Uses resolved_sonata_delay_duration_dict to handle cases where
        timestamp + timestamp_offset is negative by setting delay to 0
        and adjusting duration accordingly.

        Yields:
            Tuples of (timestamp_index, timestamp, stimulus_dict) where
            stimulus_dict contains 'delay' and 'duration' keys.
        """
        for t_ind, timestamp in enumerate(self.timestamps()):
            stim_dict = resolved_sonata_delay_duration_dict(timestamp, timestamp_offset, duration)
            yield t_ind, timestamp, stim_dict

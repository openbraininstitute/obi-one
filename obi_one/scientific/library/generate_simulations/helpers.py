from pydantic import (
    NonNegativeFloat,
)


def resolved_sonata_delay_duration_dict(
    timestamp: NonNegativeFloat, timestamp_offset: float, duration: NonNegativeFloat
) -> dict:
    """Account for the fact that SONATA does not allow for negative delay values.

    If the sum of timestamp and timestamp_offset is negative, the delay will be set to 0
    and the duration will be reduced by the absolute value of the sum of
    timestamp and timestamp_offset.

    If the sum of timestamp, timestamp_offset, and duration
    is less than or equal to 0, a ValueError is raised.
    """
    if timestamp + timestamp_offset + duration <= 0:
        msg = (
            f"Invalid stimulus configuration: timestamp ({timestamp} ms) + timestamp_offset "
            f"({timestamp_offset} ms) + duration ({duration} ms) must be > 0."
        )
        raise ValueError(msg)

    delay = max(0.0, timestamp + timestamp_offset)
    new_duration = duration
    if timestamp + timestamp_offset < 0.0:
        new_duration = duration - abs(timestamp + timestamp_offset)

    return {
        "delay": delay,
        "duration": new_duration,
    }

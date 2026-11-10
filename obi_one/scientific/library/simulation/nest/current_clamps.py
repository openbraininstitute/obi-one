"""Waveforms of the SONATA ``current_clamp`` inputs as NEST generator parameters.

A NEST generator connected with a delay of one step ``dt`` acts on a neuron one step after it
emits, so a generator time is the SONATA time minus ``dt``. NEST cannot inject before its second
step, so a window that starts earlier starts at ``2 * dt``. Times are rounded to the nearest step.
"""

from dataclasses import dataclass

import numpy as np

FIRST_STEP = 2
NA_TO_PA = 1000.0


@dataclass(frozen=True)
class Window:
    """The steps ``[start, end)`` in which an input injects current, in units of ``dt``."""

    start: int
    end: int
    anchor: float

    @classmethod
    def of(cls, delay: float, duration: float, dt: float) -> "Window":
        """The window of an input; *anchor* is its ``delay`` in ms, rounded to a step."""
        first = round(delay / dt)
        return cls(max(first, FIRST_STEP), round((delay + duration) / dt), first * dt)

    @property
    def is_empty(self) -> bool:
        return self.end <= self.start


def step_current(steps: dict[int, float], dt: float) -> dict:
    """``step_current_generator`` parameters: *steps* are ``{step: pA}``, each lasting on."""
    ordered = sorted(steps)
    return {
        "amplitude_times": [round((step - 1) * dt, 6) for step in ordered],
        "amplitude_values": [float(steps[step]) for step in ordered],
    }


def linear_steps(amp_start: float, amp_end: float, window: Window) -> dict[int, float]:
    """The current of a ramp from *amp_start* to *amp_end* nA, set at every step, in pA."""
    length = window.end - window.start
    steps = {
        window.start + j: (amp_start + (amp_end - amp_start) * j / length) * NA_TO_PA
        for j in range(length)
    }
    steps[window.end] = 0.0
    return steps


def pulse_steps(
    amp_start: float, width: float, frequency: float, delay: float, window: Window, dt: float
) -> dict[int, float]:
    """The current of a pulse train in pA: *width* ms pulses every ``1000 / frequency`` ms."""
    period = 1000.0 / frequency
    if width > period:
        msg = f"A pulse of {width} ms is longer than the period of {frequency} Hz ({period} ms)."
        raise ValueError(msg)
    width_steps = max(1, round(width / dt))
    steps: dict[int, float] = {}
    k = 0
    while (start := max(round((delay + k * period) / dt), window.start)) < window.end:
        steps[min(start + width_steps, window.end)] = 0.0
        steps[start] = amp_start * NA_TO_PA
        k += 1
    steps[window.end] = 0.0
    return steps


def sinusoidal_parameters(amp_start: float, frequency: float, window: Window, dt: float) -> dict:
    """``ac_generator`` parameters for ``amp_start * sin(2 * pi * frequency * (t - delay))``.

    NEST measures the phase from the start of the simulation, and the connection adds one step.
    """
    return {
        "amplitude": amp_start * NA_TO_PA,
        "frequency": frequency,
        "phase": float(np.mod(360.0 * frequency * (dt - window.anchor) / 1000.0, 360.0)),
        "start": round((window.start - 1) * dt, 6),
        "stop": round((window.end - 1) * dt, 6),
    }

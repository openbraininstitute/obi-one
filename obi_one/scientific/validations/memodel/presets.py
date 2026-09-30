"""OBI validation presets for MEModel entities.

Each preset returns a configured ParametricValidation instance representing
an OBI policy decision about what constitutes a valid MEModel.
"""

import math

from bluecellulab.validation import (
    EfelMeasurement,
    EqualTo,
    GreaterThan,
    IsFalse,
    ParametricValidation,
    SequenceProtocol,
    StepProtocol,
)

from obi_one.scientific.validations.memodel.config import SimulatorConfig
from obi_one.scientific.validations.memodel.names import ValidationName

_DEFAULT_REBOUND_HOLDING_CURRENT_NA = 0.04140625
_DEFAULT_REBOUND_HYPERPOLARIZATION_AMPLITUDE_NA = -0.11953125
_DEFAULT_REBOUND_HOLD_DURATION_MS = 5000.0
_DEFAULT_REBOUND_HYPERPOLARIZATION_DURATION_MS = 500.0
_DEFAULT_REBOUND_TOTAL_DURATION_MS = 25000.0


def spiking_preset() -> ParametricValidation:
    """Spiking validation: neuron must produce at least one spike at 130% rheobase."""
    return ParametricValidation(
        validation_name=ValidationName.SPIKING,
        protocol=StepProtocol(threshold_percentage=130.0),
        measurement=EfelMeasurement(feature_name="Spikecount"),
        criterion=GreaterThan(threshold=0),
        figure_filename="spiking_validation.pdf",
    )


def depolarization_block_preset() -> ParametricValidation:
    """Depolarization block: no block should occur at 200% rheobase."""
    return ParametricValidation(
        validation_name=ValidationName.DEPOLARIZATION_BLOCK,
        protocol=StepProtocol(threshold_percentage=200.0),
        measurement=EfelMeasurement(
            feature_name="depol_block_bool",
            efel_settings={"depol_block_min_duration": 150},
        ),
        criterion=IsFalse(),
        figure_filename="depolarization_block_validation.pdf",
    )


def rebound_burst_preset(
    *,
    holding_current: float | None = None,
    hyperpolarization_amplitude: float | None = None,
    hold_duration_ms: float = _DEFAULT_REBOUND_HOLD_DURATION_MS,
    expect_spikes: bool = True,
    hyperpolarization_duration_ms: float = _DEFAULT_REBOUND_HYPERPOLARIZATION_DURATION_MS,
    total_duration_ms: float = _DEFAULT_REBOUND_TOTAL_DURATION_MS,
) -> ParametricValidation:
    """Reproduce the calibrated BluePyOpt rebound-burst protocol.

    The protocol uses fixed calibrated currents rather than reconstructing them
    from input resistance. The pulse amplitude is applied on top of the holding
    current, and the phases contain absolute total currents.

    Args:
        holding_current: Calibrated baseline holding current in nA. Defaults to
            the current stored by the original BluePyOpt protocol.
        hyperpolarization_amplitude: Calibrated pulse amplitude in nA, applied
            on top of the holding current.
        hold_duration_ms: Duration of the pre-pulse holding phase in ms.
        expect_spikes: If True, pass when spikes > 0. If False, pass when spikes == 0.
        hyperpolarization_duration_ms: Duration of the hyperpolarization phase in ms.
        total_duration_ms: Total protocol duration in ms, including the release phase.

    Returns:
        A configured ParametricValidation for the rebound burst test.
    """
    resolved_holding_current = (
        _DEFAULT_REBOUND_HOLDING_CURRENT_NA if holding_current is None else float(holding_current)
    )
    resolved_hyperpolarization_amplitude = (
        _DEFAULT_REBOUND_HYPERPOLARIZATION_AMPLITUDE_NA
        if hyperpolarization_amplitude is None
        else float(hyperpolarization_amplitude)
    )
    durations = {
        "hold_duration_ms": hold_duration_ms,
        "hyperpolarization_duration_ms": hyperpolarization_duration_ms,
        "total_duration_ms": total_duration_ms,
    }
    durations = {name: float(value) for name, value in durations.items()}
    if any(not math.isfinite(value) or value <= 0.0 for value in durations.values()):
        message = "Rebound protocol durations must be positive finite numbers."
        raise ValueError(message)
    release_duration_ms = (
        durations["total_duration_ms"]
        - durations["hold_duration_ms"]
        - durations["hyperpolarization_duration_ms"]
    )
    if release_duration_ms <= 0.0:
        message = "Rebound total duration must exceed the hold and pulse durations."
        raise ValueError(message)
    if not math.isfinite(resolved_holding_current) or not math.isfinite(
        resolved_hyperpolarization_amplitude
    ):
        message = "Rebound protocol currents must be finite numbers."
        raise ValueError(message)

    # The pulse amplitude is an increment on top of the calibrated holding current.
    phases: list[tuple[float, float]] = [
        (durations["hold_duration_ms"], resolved_holding_current),
        (
            durations["hyperpolarization_duration_ms"],
            resolved_holding_current + resolved_hyperpolarization_amplitude,
        ),
        (release_duration_ms, resolved_holding_current),
    ]
    protocol = SequenceProtocol(
        phases=phases,
        pre_delay=0.0,
        post_delay=0.0,
        absolute_amplitudes=True,
        measurement_phase=2,
        add_hypamp=False,
    )

    criterion: GreaterThan | EqualTo = (
        GreaterThan(threshold=0) if expect_spikes else EqualTo(expected=0)
    )
    return ParametricValidation(
        validation_name=ValidationName.REBOUND_BURST,
        protocol=protocol,
        measurement=EfelMeasurement(feature_name="Spikecount"),
        criterion=criterion,
        figure_filename=(
            f"rebound_burst_hold{resolved_holding_current:g}nA_"
            f"amp{resolved_hyperpolarization_amplitude:g}nA_"
            f"hyper{durations['hyperpolarization_duration_ms']:g}ms.pdf"
        ),
    )


def tonic_firing_preset(
    rin: float,
    *,
    holding_voltage: float = -65.0,
    step_current: float = 0.15,
    simulator_config: SimulatorConfig,
    settle_duration: float = 500.0,
    add_hypamp: bool = True,
) -> ParametricValidation:
    """Tonic firing validation for thalamic-type neurons.

    Holding the cell at a depolarized potential (~-65 mV) before the step keeps
    the T-type Ca2+ channels inactivated, so the depolarizing step produces regular
    tonic firing from the start rather than an onset burst.

    Protocol:
        1. Hold at holding_voltage (via DC offset current from v_init)
        2. Apply a depolarizing step on top of the holding current
        3. Measure spike count during the step

    Args:
        rin: Input resistance of the cell in MOhm.
        holding_voltage: Pre-step holding potential in mV (default -65 mV to
            inactivate T-type channels).
        step_current: Absolute step current in nA applied on top of the holding
            current during the step phase.
        simulator_config: Shared simulator conditions. Its ``v_init`` is used
            for current conversion and must match global NEURON ``h.v_init``.
        settle_duration: Duration of the pre-step hold phase in ms. Longer values
            give the T-type channels more time to inactivate before the step.
        add_hypamp: Whether to add the model's calibrated holding current on top
            of the computed hold offset. Set False to avoid the onset burst caused
            by the combined current at t=0.

    Returns:
        A configured ParametricValidation for the tonic firing test.
    """
    # Holding current to bring the cell from the configured initial voltage to
    # the requested holding voltage.
    hold_offset = (
        (holding_voltage - simulator_config.v_init) / rin
        if holding_voltage != simulator_config.v_init
        else 0.0
    )

    # Two phases: hold (settle_duration to equilibrate) → step (1350ms, measured)
    phases: list[tuple[float, float]] = [
        (settle_duration, hold_offset),  # Phase 0: pre-hold (inactivate T-type)
        (1350.0, hold_offset + step_current),  # Phase 1: depolarizing step (measured)
    ]

    protocol = SequenceProtocol(
        phases=phases,
        pre_delay=0.0,
        post_delay=250.0,
        absolute_amplitudes=True,
        measurement_phase=1,  # Count spikes during the step
        add_hypamp=add_hypamp,
    )

    return ParametricValidation(
        # Same name as spiking_preset() — this is the thalamic variant of the
        # spiking validation (holds at -65 mV first). A given cell runs one or
        # the other, so the platform sees a single "Spiking Validation" result.
        validation_name=ValidationName.SPIKING,
        protocol=protocol,
        measurement=EfelMeasurement(feature_name="Spikecount"),
        criterion=GreaterThan(threshold=0),
        figure_filename="tonic_firing_validation.pdf",
    )

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

from obi_one.scientific.validations.memodel.names import ValidationName

_DEFAULT_REBOUND_HOLDING_CURRENT_NA = 0.04140625
_DEFAULT_REBOUND_HYPERPOLARIZATION_AMPLITUDE_NA = -0.11953125
_DEFAULT_REBOUND_HOLD_DURATION_MS = 5000.0
_DEFAULT_REBOUND_HYPERPOLARIZATION_DURATION_MS = 500.0
_DEFAULT_REBOUND_TOTAL_DURATION_MS = 25000.0
# Stimulus waveform resolution for the rebound protocol. The calibrated
# BluePyOpt rebound was reproduced at 0.1 ms; a coarser grid shifts the release
# edge and can misresolve the burst on these stiff thalamic models.
_REBOUND_DT_MS = 0.1


def spiking_preset() -> ParametricValidation:
    """Spiking validation: neuron must produce at least one spike at 130% rheobase."""
    return ParametricValidation(
        validation_name=ValidationName.SPIKING,
        protocol=StepProtocol(threshold_percentage=130.0),
        measurement=EfelMeasurement(feature_name="Spikecount", efel_settings={"Threshold": -40.0}),
        criterion=GreaterThan(threshold=0),
        figure_filename="spiking_validation.pdf",
    )


def depolarization_block_preset() -> ParametricValidation:
    """Depolarization block: no block should occur at 200% rheobase.

    Steps from rest. Correct for cells that fire tonically from rest. For
    intrinsic bursters (e.g. thalamic reticular neurons), use
    ``thalamic_depolarization_block_preset`` instead, which pre-holds the cell
    depolarized so the step produces tonic firing rather than a rebound burst.
    """
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


def thalamic_depolarization_block_preset(
    rheobase: float,
    holding_current: float,
    *,
    step_percentage: float = 200.0,
    settle_duration: float = 500.0,
    step_duration: float = 1350.0,
) -> ParametricValidation:
    """Depolarization block for intrinsic bursters, with a depolarized pre-hold.

    Holding the cell at a depolarized potential (~-65 mV) before the step keeps
    the T-type Ca2+ channels inactivated, so the step produces regular tonic
    firing rather than a rebound burst. Without the pre-hold, the burst rides on
    a slow plateau that eFEL's ``depol_block_bool`` misreads as block. With it,
    the step shows tonic firing and the plain eFEL feature judges block
    correctly.

    Protocol:
        1. Hold at ``holding_current`` (derived by setup to reach the profile's
           target holding voltage).
        2. Apply a step at ``step_percentage`` of rheobase on top of the hold.
        3. Measure depolarization block during the step.

    Args:
        rheobase: The model's rheobase in nA, used to size the step.
        holding_current: Absolute holding current in nA that brings the cell to
            the target holding voltage, derived by the workflow. Applied for the
            whole protocol so the step sits on top of the hold.
        step_percentage: Step amplitude as a percentage of rheobase (default
            200%, matching the default depolarization-block protocol).
        settle_duration: Duration of the pre-step hold phase in ms.
        step_duration: Duration of the measured step phase in ms.

    Returns:
        A configured ParametricValidation for the thalamic depolarization-block
        test.
    """
    step_current = rheobase * step_percentage / 100.0

    # Two phases, both absolute current: hold to inactivate T-type, then the
    # suprathreshold step on top of the hold. Measure block during the step.
    # add_hypamp is False because holding_current already sets the hold; the
    # models carry no separate calibrated holding to add.
    phases: list[tuple[float, float]] = [
        (settle_duration, holding_current),
        (step_duration, holding_current + step_current),
    ]

    protocol = SequenceProtocol(
        phases=phases,
        pre_delay=0.0,
        post_delay=250.0,
        amplitude_mode="amplitude",
        measurement_phase=1,
        add_hypamp=False,
    )

    return ParametricValidation(
        validation_name=ValidationName.DEPOLARIZATION_BLOCK,
        protocol=protocol,
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
        amplitude_mode="amplitude",
        measurement_phase=2,
        add_hypamp=False,
        dt=_REBOUND_DT_MS,
    )

    criterion: GreaterThan | EqualTo = (
        GreaterThan(threshold=0) if expect_spikes else EqualTo(expected=0)
    )
    return ParametricValidation(
        validation_name=ValidationName.REBOUND_BURST,
        protocol=protocol,
        measurement=EfelMeasurement(feature_name="Spikecount", efel_settings={"Threshold": -40.0}),
        criterion=criterion,
        figure_filename=(
            f"rebound_burst_hold{resolved_holding_current:g}nA_"
            f"amp{resolved_hyperpolarization_amplitude:g}nA_"
            f"hyper{durations['hyperpolarization_duration_ms']:g}ms.pdf"
        ),
    )


def tonic_firing_preset(
    holding_current: float,
    *,
    step_current: float = 0.4,
    settle_duration: float = 500.0,
) -> ParametricValidation:
    """Tonic firing validation for thalamic-type neurons.

    Holding the cell at a depolarized potential (~-60 mV) before the step keeps
    the T-type Ca2+ channels inactivated, so the depolarizing step produces regular
    tonic firing from the start rather than an onset burst. The -60 mV hold and
    0.4 nA (400 pA) step match the source ephys protocol (Hartley et al.,
    Cell Reports 2024, Figure 2O-R).

    Protocol:
        1. Hold at holding_current (derived by setup to reach the target voltage)
        2. Apply a depolarizing step on top of the holding current
        3. Measure spike count during the step

    Args:
        holding_current: Absolute holding current in nA that brings the cell to
            the target holding voltage, derived by the workflow.
        step_current: Absolute step current in nA applied on top of the holding
            current during the step phase.
        settle_duration: Duration of the pre-step hold phase in ms. Longer values
            give the T-type channels more time to inactivate before the step.

    Returns:
        A configured ParametricValidation for the tonic firing test.
    """
    # Two phases: hold (settle_duration to equilibrate) → step (1350ms, measured).
    # add_hypamp is False because holding_current already sets the hold.
    phases: list[tuple[float, float]] = [
        (settle_duration, holding_current),  # Phase 0: pre-hold (inactivate T-type)
        (1350.0, holding_current + step_current),  # Phase 1: depolarizing step (measured)
    ]

    protocol = SequenceProtocol(
        phases=phases,
        pre_delay=0.0,
        post_delay=250.0,
        amplitude_mode="amplitude",
        measurement_phase=1,  # Count spikes during the step
        add_hypamp=False,
    )

    return ParametricValidation(
        # Same name as spiking_preset() — this is the thalamic variant of the
        # spiking validation (holds at -65 mV first). A given cell runs one or
        # the other, so the platform sees a single "Spiking Validation" result.
        validation_name=ValidationName.SPIKING,
        protocol=protocol,
        measurement=EfelMeasurement(feature_name="Spikecount", efel_settings={"Threshold": -40.0}),
        criterion=GreaterThan(threshold=0),
        figure_filename="tonic_firing_validation.pdf",
    )

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

_DEFAULT_REBOUND_HYPERPOLARIZATION_DURATION_MS = 500.0


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
    rin: float,
    *,
    holding_voltage: float = -65.0,
    target_voltage: float = -110.0,
    simulator_config: SimulatorConfig,
    expect_spikes: bool = True,
    hyperpolarization_duration_ms: float = _DEFAULT_REBOUND_HYPERPOLARIZATION_DURATION_MS,
) -> ParametricValidation:
    """Thalamic rebound burst validation (Hartley et al. 2024).

    Protocol:
        1. Hold at holding_voltage (via DC offset current from v_init)
        2. Hyperpolarize for ``hyperpolarization_duration_ms`` to target_voltage
           (de-inactivate T-type Ca2+)
        3. Release back to holding_voltage for 1000 ms (observe rebound burst)

    All currents are computed from the cell's input resistance:
        I = (V_target - V_source) / Rin

    Args:
        rin: Input resistance of the cell in MOhm.
        holding_voltage: Holding potential in mV (default -65 mV for burst scenario).
        target_voltage: Hyperpolarization target in mV (default -110 mV).
        simulator_config: Shared simulator conditions. Its ``v_init`` is used
            for current conversion and must match global NEURON ``h.v_init``.
        expect_spikes: If True, pass when spikes > 0. If False, pass when spikes == 0.
        hyperpolarization_duration_ms: Duration of the hyperpolarization phase in
            ms. Defaults to 500 ms to preserve the established protocol.

    Returns:
        A configured ParametricValidation for the rebound burst test.
    """
    if isinstance(hyperpolarization_duration_ms, bool):
        message = "hyperpolarization_duration_ms must be a positive finite number."
        raise TypeError(message)
    try:
        hyperpolarization_duration_ms = float(hyperpolarization_duration_ms)
    except (TypeError, ValueError) as error:
        message = "hyperpolarization_duration_ms must be a positive finite number."
        raise TypeError(message) from error
    if not math.isfinite(hyperpolarization_duration_ms) or hyperpolarization_duration_ms <= 0.0:
        message = "hyperpolarization_duration_ms must be a positive finite number."
        raise ValueError(message)

    # Compute currents from Rin (Ohm's law: I = dV / R)
    hold_offset = (
        (holding_voltage - simulator_config.v_init) / rin
        if holding_voltage != simulator_config.v_init
        else 0.0
    )
    hyperpol_current = (target_voltage - holding_voltage) / rin

    # Three phases: hold (250ms) → hyperpolarize → release (1000ms)
    phases: list[tuple[float, float]] = [
        (250.0, hold_offset),  # Phase 0: pre-hold (equilibrate)
        (
            hyperpolarization_duration_ms,
            hold_offset + hyperpol_current,
        ),  # Phase 1: hyperpolarization
        (1000.0, hold_offset),  # Phase 2: release (measurement window)
    ]

    protocol = SequenceProtocol(
        phases=phases,
        pre_delay=0.0,
        post_delay=250.0,
        absolute_amplitudes=True,
        measurement_phase=2,  # Count spikes only during release
        add_hypamp=True,
    )

    criterion: GreaterThan | EqualTo = (
        GreaterThan(threshold=0) if expect_spikes else EqualTo(expected=0)
    )

    # Both the burst-expected test and the negative control (expect_spikes=False,
    # typically held at -80 mV) use the single controlled-vocabulary name. The
    # control is meant to be run for inspection only, never registered, so the
    # shared name does not cause a registration collision.
    duration_suffix = (
        f"_hyper{hyperpolarization_duration_ms:g}ms"
        if not math.isclose(
            hyperpolarization_duration_ms,
            _DEFAULT_REBOUND_HYPERPOLARIZATION_DURATION_MS,
        )
        else ""
    )
    return ParametricValidation(
        validation_name=ValidationName.REBOUND_BURST,
        protocol=protocol,
        measurement=EfelMeasurement(feature_name="Spikecount"),
        criterion=criterion,
        figure_filename=(
            f"rebound_burst_hold{holding_voltage:g}mV_"
            f"target{target_voltage:g}mV{duration_suffix}.pdf"
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

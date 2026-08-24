"""OBI validation presets for MEModel entities.

Each preset returns a configured ParametricValidation instance representing
an OBI policy decision about what constitutes a valid MEModel.
"""

from bluecellulab.validation import (
    EfelMeasurement,
    EqualTo,
    GreaterThan,
    IsFalse,
    ParametricValidation,
    SequenceProtocol,
    StepProtocol,
)


def spiking_preset() -> ParametricValidation:
    """Spiking validation: neuron must produce at least one spike at 130% rheobase."""
    return ParametricValidation(
        validation_name="Simulatable Neuron Spiking Validation",
        protocol=StepProtocol(threshold_percentage=130.0),
        measurement=EfelMeasurement(feature_name="Spikecount"),
        criterion=GreaterThan(threshold=0),
        figure_filename="spiking_validation.pdf",
    )


def depolarization_block_preset() -> ParametricValidation:
    """Depolarization block: no block should occur at 200% rheobase."""
    return ParametricValidation(
        validation_name="Simulatable Neuron Depolarization Block Validation",
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
    target_voltage: float = -105.0,
    v_init: float = -80.0,
    expect_spikes: bool = True,
) -> ParametricValidation:
    """Thalamic rebound burst validation (Hartley et al. 2024).

    Protocol:
        1. Hold at holding_voltage (via DC offset current from v_init)
        2. Hyperpolarize for 500 ms to target_voltage (de-inactivate T-type Ca2+)
        3. Release back to holding_voltage for 1000 ms (observe rebound burst)

    All currents are computed from the cell's input resistance:
        I = (V_target - V_source) / Rin

    Args:
        rin: Input resistance of the cell in MOhm.
        holding_voltage: Holding potential in mV (default -65 mV for burst scenario).
        target_voltage: Hyperpolarization target in mV.
        v_init: Resting potential / v_init used in simulation globals.
        expect_spikes: If True, pass when spikes > 0. If False, pass when spikes == 0.

    Returns:
        A configured ParametricValidation for the rebound burst test.
    """
    # Compute currents from Rin (Ohm's law: I = dV / R)
    hold_offset = (holding_voltage - v_init) / rin if holding_voltage != v_init else 0.0
    hyperpol_current = (target_voltage - holding_voltage) / rin

    # Three phases: hold (250ms) → hyperpolarize (500ms) → release (1000ms)
    phases: list[tuple[float, float]] = [
        (250.0, hold_offset),                       # Phase 0: pre-hold (equilibrate)
        (500.0, hold_offset + hyperpol_current),    # Phase 1: hyperpolarization
        (1000.0, hold_offset),                      # Phase 2: release (measurement window)
    ]

    protocol = SequenceProtocol(
        phases=phases,
        pre_delay=0.0,
        post_delay=250.0,
        absolute_amplitudes=True,
        measurement_phase=2,  # Count spikes only during release
        add_hypamp=True,
    )

    criterion: GreaterThan | EqualTo
    if expect_spikes:
        criterion = GreaterThan(threshold=0)
    else:
        criterion = EqualTo(expected=0)

    burst_label = "expect burst" if expect_spikes else "expect no burst"
    name = "Simulatable Neuron Rebound Burst Validation"
    if not expect_spikes:
        name = f"{name} ({burst_label})"

    return ParametricValidation(
        validation_name=name,
        protocol=protocol,
        measurement=EfelMeasurement(feature_name="Spikecount"),
        criterion=criterion,
        figure_filename=f"rebound_burst_hold{int(holding_voltage)}mV.pdf",
    )


def tonic_firing_preset(
    rin: float,
    *,
    holding_voltage: float = -65.0,
    step_current: float = 0.15,
    v_init: float = -80.0,
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
        v_init: Resting potential / v_init used in simulation globals.
        settle_duration: Duration of the pre-step hold phase in ms. Longer values
            give the T-type channels more time to inactivate before the step.
        add_hypamp: Whether to add the model's calibrated holding current on top
            of the computed hold offset. Set False to avoid the onset burst caused
            by the combined current at t=0.

    Returns:
        A configured ParametricValidation for the tonic firing test.
    """
    # Holding current to bring the cell from v_init to holding_voltage
    hold_offset = (holding_voltage - v_init) / rin if holding_voltage != v_init else 0.0

    # Two phases: hold (settle_duration to equilibrate) → step (1350ms, measured)
    phases: list[tuple[float, float]] = [
        (settle_duration, hold_offset),          # Phase 0: pre-hold (inactivate T-type)
        (1350.0, hold_offset + step_current),    # Phase 1: depolarizing step (measured)
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
        validation_name="Simulatable Neuron Spiking Validation",
        protocol=protocol,
        measurement=EfelMeasurement(feature_name="Spikecount"),
        criterion=GreaterThan(threshold=0),
        figure_filename="tonic_firing_validation.pdf",
    )

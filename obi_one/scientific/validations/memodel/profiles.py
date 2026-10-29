"""Reusable validation profiles for MEModel workflows.

A profile owns validation policy: the context data it requires and the tests it
constructs. The MEModel workflow remains responsible for preparing the model,
executing tests, and registering results.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

from obi_one.scientific.validations.base import InvalidValidationContextError
from obi_one.scientific.validations.memodel.config import (
    DEFAULT_SIMULATOR_CONFIG,
    THALAMIC_SIMULATOR_CONFIG,
    SimulatorConfig,
)
from obi_one.scientific.validations.memodel.presets import (
    depolarization_block_preset,
    rebound_burst_preset,
    spiking_preset,
    thalamic_depolarization_block_preset,
    tonic_firing_preset,
)
from obi_one.scientific.validations.memodel.tests import (
    AISSpikingTest,
    BPAPTest,
    FICurveTest,
    HyperpolarizationTest,
    IVCurveTest,
    RinTest,
)

if TYPE_CHECKING:
    from bluecellulab.validation.base import ValidationTest

    from obi_one.scientific.validations.memodel.workflow import MEModelWorkflowContext


def _optional_finite(name: str, value: float | None) -> float | None:
    """Return ``value`` as a finite float, or None, rejecting invalid input."""
    if value is None:
        return None
    message = f"{name} must be a finite number or None."
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise TypeError(message) from error
    if not math.isfinite(numeric):
        raise ValueError(message)
    return numeric


def _positive_finite(name: str, value: float) -> float:
    """Return ``value`` as a positive finite float, rejecting invalid input."""
    message = f"{name} must be a positive finite number."
    if isinstance(value, bool):
        raise TypeError(message)
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise TypeError(message) from error
    if not math.isfinite(numeric) or numeric <= 0.0:
        raise ValueError(message)
    return numeric


class MEModelValidationProfile(ABC):
    """Base class for an MEModel validation policy.

    Subclasses define the tests for a validation scenario and may declare that
    input resistance or a calibrated holding current is required by overriding
    :attr:`requires_rin` or :attr:`requires_holding_current`. Custom profiles
    can be passed directly to :class:`MEModelValidationWorkflow`.
    """

    profile_name: ClassVar[str] = "custom"
    simulator_config_fallback: ClassVar[SimulatorConfig] = DEFAULT_SIMULATOR_CONFIG

    @property
    def requires_rin(self) -> bool:
        """Whether workflow setup must calculate input resistance."""
        return False

    @property
    def requires_holding_current(self) -> bool:
        """Whether a nonzero calibrated holding current is required.

        Default False: a missing calibration holding resolves to 0.0 nA (no
        holding). Override to True only for profiles whose protocols cannot run
        meaningfully without a calibrated holding; a missing value then raises
        instead of defaulting to 0.0.
        """
        return False

    @property
    def recompute_rheobase(self) -> bool:
        """Whether setup must compute rheobase instead of trusting calibration.

        Default False: use ``calibration_result.threshold_current`` when present.
        Override to True for profiles that run percentage-scaled step protocols
        (e.g. the FI curve), where the rheobase must be the model's true firing
        threshold at the HOC conditions. The registered calibration may carry a
        placeholder or a value computed at the wrong temperature, which breaks
        rheobase-scaled sweeps; recomputing at the HOC conditions avoids that.
        """
        return False

    @property
    def holding_voltage(self) -> float | None:
        """Pre-step holding potential in mV, or None to step from rest.

        Default None: protocols step from the cell's resting potential, which is
        correct for cells that fire tonically from rest. Override to a target
        voltage for cell classes that must be held depolarized before the step
        (e.g. thalamic neurons held at ~-65 mV to inactivate T-type Ca so the
        step produces tonic firing rather than a rebound burst). When set, setup
        derives the holding current that reaches this voltage and stores it on
        the context for the profile's pre-held protocols.
        """
        return None

    def validate_context(self, context: MEModelWorkflowContext) -> None:
        """Validate context data required by this profile."""
        if self.requires_rin and (
            context.rin is None or not math.isfinite(context.rin) or context.rin <= 0.0
        ):
            message = f"Validation profile '{self.profile_name}' requires a positive finite Rin."
            raise InvalidValidationContextError(message)

    @staticmethod
    @abstractmethod
    def build_tests(context: MEModelWorkflowContext) -> list[ValidationTest]:
        """Build the tests for this profile from the prepared workflow context."""
        raise NotImplementedError


class DefaultMEModelValidationProfile(MEModelValidationProfile):
    """Default MEModel validation profile."""

    profile_name = "default"

    @staticmethod
    def build_tests(context: MEModelWorkflowContext) -> list[ValidationTest]:
        """Build the standard spiking and depolarization-block validations."""
        _ = context
        return [
            spiking_preset(),
            depolarization_block_preset(),
        ]


class ThalamicMEModelValidationProfile(MEModelValidationProfile):
    """Complete legacy-compatible profile for thalamic validation."""

    profile_name = "thalamic"
    simulator_config_fallback = THALAMIC_SIMULATOR_CONFIG

    def __init__(
        self,
        *,
        bpap_holding_current: float | None = None,
        bpap_amplitude_factor: float = 30.0,
        bpap_amplitude: float | None = None,
        bpap_trace_diagnostics: bool = False,
        rebound_holding_current: float | None = None,
        rebound_hyperpolarization_amplitude: float | None = None,
        rebound_hyperpolarization_duration_ms: float = 500.0,
    ) -> None:
        """Configure optional model-specific BPAP and rebound settings.

        ``bpap_holding_current`` is used only by BPAP. When omitted, BPAP uses
        the calibrated holding current carried by the model's template
        parameters. Set this explicitly for trial protocols whose calibration
        metadata is zero or unavailable, for example 0.065 nA for the Ecel1
        trial or 0.040 nA for Spp variants.

        ``bpap_amplitude_factor`` scales rheobase for the BPAP pulse. Used only
        when ``bpap_amplitude`` is not set.

        ``bpap_amplitude`` is an absolute BPAP pulse amplitude in nA. When set,
        it takes precedence over ``bpap_amplitude_factor`` so the pulse does not
        scale with rheobase. Preferred for thalamic cells: a single AP is set by
        the depolarized holding (which inactivates T-type Ca), not by the pulse
        size, so an absolute amplitude (~0.6 nA) gives one AP robustly across
        models regardless of their rheobase.

        ``bpap_trace_diagnostics`` appends pulse-adjacent soma-voltage metrics
        to the BPAP result details without changing the protocol or outcome.

        ``rebound_holding_current`` and ``rebound_hyperpolarization_amplitude``
        are the calibrated BluePyOpt rebound-burst currents in nA. They are
        per-model: each thalamic emodel has its own values from its
        ``Step_ReboundBurst_burst`` protocol (e.g. holding 0.04921875 nA /
        pulse -0.14140625 nA for Spp, 0.0875 / -0.246484375 for Ecel1). When
        omitted, the preset defaults apply, which only reproduce the Spp_runaway
        rebound; set both explicitly for every other model.

        ``rebound_hyperpolarization_duration_ms`` controls only the rebound
        hyperpolarization phase. It defaults to 500 ms to preserve the
        established thalamic protocol.
        """
        if not isinstance(bpap_trace_diagnostics, bool):
            message = "bpap_trace_diagnostics must be a boolean."
            raise TypeError(message)
        self.bpap_holding_current = _optional_finite("bpap_holding_current", bpap_holding_current)
        self.bpap_amplitude_factor = _positive_finite(
            "bpap_amplitude_factor", bpap_amplitude_factor
        )
        self.bpap_amplitude = _optional_finite("bpap_amplitude", bpap_amplitude)
        self.bpap_trace_diagnostics = bpap_trace_diagnostics
        self.rebound_holding_current = _optional_finite(
            "rebound_holding_current", rebound_holding_current
        )
        self.rebound_hyperpolarization_amplitude = _optional_finite(
            "rebound_hyperpolarization_amplitude", rebound_hyperpolarization_amplitude
        )
        self.rebound_hyperpolarization_duration_ms = _positive_finite(
            "rebound_hyperpolarization_duration_ms", rebound_hyperpolarization_duration_ms
        )

    @property
    def requires_rin(self) -> bool:
        return True

    @property
    def requires_holding_current(self) -> bool:
        return True

    @property
    def recompute_rheobase(self) -> bool:
        # The FI curve sweeps rheobase -> 3x rheobase, so it needs the model's
        # true firing threshold. The registered calibration carries a shared
        # lower-bound placeholder (~0.02 nA), not the per-model rheobase.
        return True

    @property
    def holding_voltage(self) -> float:
        # Thalamic neurons are held at -60 mV before the step to inactivate
        # T-type Ca, so the spiking and depolarization-block steps produce
        # regular tonic firing rather than a rebound burst. -60 mV and the
        # 0.4 nA tonic step match the source ephys protocol (Hartley et al.,
        # Cell Reports 2024, Figure 2O-R: neurons held at -60 mV, tonic firing
        # characterized with depolarizing steps, representative traces at 400 pA).
        return -60.0

    def build_tests(self, context: MEModelWorkflowContext) -> list[ValidationTest]:
        """Build the complete nine-test thalamic validation policy."""
        self.validate_context(context)
        rin = context.rin
        if rin is None:
            message = f"Validation profile '{self.profile_name}' requires a positive finite Rin."
            raise InvalidValidationContextError(message)
        simulator_config = context.simulator_config or self.simulator_config_fallback
        rheobase = context.rheobase
        if rheobase is None:
            message = (
                f"Validation profile '{self.profile_name}' requires a rheobase to size the "
                "depolarization-block step."
            )
            raise InvalidValidationContextError(message)
        holding_current = context.holding_current
        if holding_current is None:
            message = (
                f"Validation profile '{self.profile_name}' requires a derived holding current "
                "to pre-hold the cell; setup did not provide one."
            )
            raise InvalidValidationContextError(message)
        return [
            # Tonic firing uses a depolarized hold to inactivate T-type Ca,
            # then a 0.4 nA (400 pA) step, matching the source ephys protocol.
            tonic_firing_preset(
                holding_current=holding_current,
                step_current=0.4,
            ),
            # Depolarization block uses the same depolarized hold so the step
            # produces tonic firing rather than a rebound burst.
            thalamic_depolarization_block_preset(
                rheobase=rheobase,
                holding_current=holding_current,
            ),
            rebound_burst_preset(
                holding_current=self.rebound_holding_current,
                hyperpolarization_amplitude=self.rebound_hyperpolarization_amplitude,
                hyperpolarization_duration_ms=(self.rebound_hyperpolarization_duration_ms),
                expect_spikes=True,
            ),
            # BlueCelluLab validation equivalents.
            # The full-trace guard prevents a late rebound burst from being
            # hidden by BlueCelluLab's pulse-centered recording plot.
            BPAPTest(
                amplitude_factor=self.bpap_amplitude_factor,
                amplitude=self.bpap_amplitude,
                stim_duration=2.0,
                holding_current=self.bpap_holding_current,
                expected_spike_count=1,
                trace_diagnostics=self.bpap_trace_diagnostics,
                simulator_config=simulator_config,
            ),
            AISSpikingTest(),
            HyperpolarizationTest(),
            RinTest(rin=rin),
            IVCurveTest(n_processes=None, simulator_config=simulator_config),
            FICurveTest(n_processes=None, simulator_config=simulator_config),
        ]


_PROFILE_TYPES: dict[str, type[MEModelValidationProfile]] = {
    DefaultMEModelValidationProfile.profile_name: DefaultMEModelValidationProfile,
    ThalamicMEModelValidationProfile.profile_name: ThalamicMEModelValidationProfile,
}


def register_validation_profile(
    name: str,
    profile_type: type[MEModelValidationProfile],
    *,
    overwrite: bool = False,
) -> None:
    """Register a named profile type for task configuration resolution."""
    if not name.strip():
        message = "Validation profile name cannot be empty."
        raise ValueError(message)
    if not issubclass(profile_type, MEModelValidationProfile):
        message = "profile_type must inherit from MEModelValidationProfile."
        raise TypeError(message)

    key = name.strip()
    if key in _PROFILE_TYPES and not overwrite:
        message = f"Validation profile '{key}' is already registered."
        raise ValueError(message)
    _PROFILE_TYPES[key] = profile_type


def get_validation_profile(
    profile: str | MEModelValidationProfile | None = None,
) -> MEModelValidationProfile:
    """Resolve a profile name or return a supplied profile instance."""
    if profile is None:
        return DefaultMEModelValidationProfile()
    if isinstance(profile, MEModelValidationProfile):
        return profile
    if not isinstance(profile, str):
        message = "profile must be a profile name or MEModelValidationProfile instance."
        raise TypeError(message)

    try:
        profile_type = _PROFILE_TYPES[profile.strip()]
    except KeyError as error:
        available = ", ".join(sorted(_PROFILE_TYPES))
        message = (
            f"Unknown MEModel validation profile '{profile}'. Available profiles: {available}."
        )
        raise ValueError(message) from error
    return profile_type()

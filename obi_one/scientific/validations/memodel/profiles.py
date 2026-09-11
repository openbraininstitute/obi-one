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
        """Whether workflow setup must provide calibrated holding current."""
        return False

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
        bpap_trace_diagnostics: bool = False,
        rebound_hyperpolarization_duration_ms: float = 500.0,
    ) -> None:
        """Configure optional model-specific BPAP settings.

        ``bpap_holding_current`` is used only by BPAP. When omitted, BPAP uses
        the calibrated holding current carried by the model's template
        parameters. Set this explicitly for trial protocols whose calibration
        metadata is zero or unavailable, for example 0.065 nA for the Ecel1
        trial or 0.040 nA for Spp variants.

        ``bpap_amplitude_factor`` scales rheobase for the BPAP pulse. It
        defaults to the tested thalamic value of 30.0; model-specific
        overrides must be explicitly configured and verified.

        ``bpap_trace_diagnostics`` appends pulse-adjacent soma-voltage metrics
        to the BPAP result details without changing the protocol or outcome.

        ``rebound_hyperpolarization_duration_ms`` controls only the rebound
        hyperpolarization phase. It defaults to 500 ms to preserve the
        established thalamic protocol.
        """
        if bpap_holding_current is not None:
            try:
                bpap_holding_current = float(bpap_holding_current)
            except (TypeError, ValueError) as error:
                message = "bpap_holding_current must be a finite number or None."
                raise TypeError(message) from error
            if not math.isfinite(bpap_holding_current):
                message = "bpap_holding_current must be a finite number or None."
                raise ValueError(message)
        try:
            bpap_amplitude_factor = float(bpap_amplitude_factor)
        except (TypeError, ValueError) as error:
            message = "bpap_amplitude_factor must be a positive finite number."
            raise TypeError(message) from error
        if not math.isfinite(bpap_amplitude_factor) or bpap_amplitude_factor <= 0.0:
            message = "bpap_amplitude_factor must be a positive finite number."
            raise ValueError(message)
        if not isinstance(bpap_trace_diagnostics, bool):
            message = "bpap_trace_diagnostics must be a boolean."
            raise TypeError(message)
        if isinstance(rebound_hyperpolarization_duration_ms, bool):
            message = "rebound_hyperpolarization_duration_ms must be a positive finite number."
            raise TypeError(message)
        try:
            rebound_hyperpolarization_duration_ms = float(rebound_hyperpolarization_duration_ms)
        except (TypeError, ValueError) as error:
            message = "rebound_hyperpolarization_duration_ms must be a positive finite number."
            raise TypeError(message) from error
        if (
            not math.isfinite(rebound_hyperpolarization_duration_ms)
            or rebound_hyperpolarization_duration_ms <= 0.0
        ):
            message = "rebound_hyperpolarization_duration_ms must be a positive finite number."
            raise ValueError(message)
        self.bpap_holding_current = bpap_holding_current
        self.bpap_amplitude_factor = bpap_amplitude_factor
        self.bpap_trace_diagnostics = bpap_trace_diagnostics
        self.rebound_hyperpolarization_duration_ms = rebound_hyperpolarization_duration_ms

    @property
    def requires_rin(self) -> bool:
        return True

    @property
    def requires_holding_current(self) -> bool:
        return True

    def build_tests(self, context: MEModelWorkflowContext) -> list[ValidationTest]:
        """Build the complete nine-test thalamic validation policy."""
        self.validate_context(context)
        rin = context.rin
        if rin is None:
            message = f"Validation profile '{self.profile_name}' requires a positive finite Rin."
            raise InvalidValidationContextError(message)
        simulator_config = context.simulator_config or self.simulator_config_fallback
        return [
            # Tonic firing uses a depolarized hold to inactivate T-type Ca.
            tonic_firing_preset(
                rin=rin,
                holding_voltage=-65.0,
                step_current=0.15,
                simulator_config=simulator_config,
                add_hypamp=True,
            ),
            depolarization_block_preset(),
            rebound_burst_preset(
                rin=rin,
                holding_voltage=-65.0,
                target_voltage=-100.0,
                hyperpolarization_duration_ms=(self.rebound_hyperpolarization_duration_ms),
                simulator_config=simulator_config,
                expect_spikes=True,
            ),
            # BlueCelluLab validation equivalents.
            # The full-trace guard prevents a late rebound burst from being
            # hidden by BlueCelluLab's pulse-centered recording plot.
            BPAPTest(
                amplitude_factor=self.bpap_amplitude_factor,
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

"""Plain-text descriptions of the protocol each MEModel validation actually ran.

They are stored as ``ValidationResult.description`` so the platform can show what was
run instead of a fixed text per validation name. They are generated from the same
protocol and criterion objects the test executes, so they cannot drift from it.
"""

from abc import ABC, abstractmethod

from bluecellulab.stimulus.factory import IDRestTimings
from bluecellulab.validation.base import ValidationTest
from bluecellulab.validation.criterion import Criterion, EqualTo, GreaterThan, IsFalse
from bluecellulab.validation.measurement import EfelMeasurement, Measurement
from bluecellulab.validation.parametric_validation import ParametricValidation
from bluecellulab.validation.protocol import Protocol, SequenceProtocol, StepProtocol


def format_current(amplitude_na: float) -> str:
    """Format a current in nA with enough digits for per-model currents."""
    return f"{amplitude_na:.4g} nA"


def format_rheobase_percentage(percentage: float) -> str:
    """Format an amplitude given as a percentage of rheobase."""
    return f"{percentage:g}% of rheobase"


def format_setting(value: object) -> str:
    """Format an eFEL setting, dropping trailing zeros from numbers."""
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def holding_note(holding_current: float) -> str:
    """Describe the holding current a protocol is applied on top of."""
    if not holding_current:
        return "with no holding current"
    return f"on top of a holding current of {format_current(holding_current)}"


def describe_location(section: str) -> str:
    """Name the injection site in words when it is the soma."""
    return "the soma" if section.startswith("soma") else section


def describe_step_protocol(protocol: StepProtocol, holding_current: float) -> str:
    """Describe an IDRest-style step protocol."""
    amplitude = (
        format_current(protocol.amplitude)
        if protocol.amplitude is not None
        else format_rheobase_percentage(protocol.threshold_percentage)
    )
    holding = f", {holding_note(holding_current)}," if protocol.add_hypamp else ""
    return (
        f"Injects a step of {amplitude} into {describe_location(protocol.section)}{holding} "
        f"for {IDRestTimings.DURATION.value:g} ms, after {IDRestTimings.PRE_DELAY.value:g} ms "
        f"and followed by {IDRestTimings.POST_DELAY.value:g} ms."
    )


def describe_sequence_protocol(
    protocol: SequenceProtocol,
    holding_current: float,
    *,
    mark_measured: bool = True,
) -> str:
    """Describe a multi-phase protocol, phase by phase.

    Args:
        protocol: The protocol to describe.
        holding_current: Holding current in nA applied when the protocol adds it.
        mark_measured: Whether to mark the phase the measurement is taken from.
    """
    phases = []
    for index, (duration, amplitude) in enumerate(protocol.phases):
        if protocol.amplitude_mode == "amplitude":
            if protocol.add_hypamp and not amplitude:
                value = "with no added current"
            else:
                value = f"at {format_current(amplitude)}"
        else:
            value = f"at {format_rheobase_percentage(amplitude)}"
        measured = " (measured)" if mark_measured and index == protocol.measurement_phase else ""
        phases.append(f"{duration:g} ms {value}{measured}")
    if protocol.add_hypamp:
        injection = f", {holding_note(holding_current)}"
    else:
        injection = " (total current, including any holding)"
    text = f"Injects into {describe_location(protocol.section)}{injection}: " + ", then ".join(
        phases
    )
    if protocol.pre_delay:
        text += f", after {protocol.pre_delay:g} ms"
    if protocol.post_delay:
        text += f", followed by {protocol.post_delay:g} ms"
    return f"{text}."


def describe_protocol(
    protocol: Protocol,
    holding_current: float,
    *,
    mark_measured: bool = True,
) -> str:
    """Describe a BlueCelluLab protocol, or return "" for unknown protocol types."""
    if isinstance(protocol, StepProtocol):
        return describe_step_protocol(protocol, holding_current)
    if isinstance(protocol, SequenceProtocol):
        return describe_sequence_protocol(protocol, holding_current, mark_measured=mark_measured)
    return ""


def describe_measurement(measurement: Measurement) -> str:
    """Name what is measured, including non-default eFEL settings."""
    if isinstance(measurement, EfelMeasurement):
        text = f"the eFEL feature {measurement.feature_name}"
        if measurement.efel_settings:
            settings = ", ".join(
                f"{key}={format_setting(value)}" for key, value in measurement.efel_settings.items()
            )
            text += f" ({settings})"
        return text
    return "the measured value"


def describe_criterion(measurement: Measurement, criterion: Criterion) -> str:
    """Describe the pass condition, or return "" for unknown criterion types."""
    measured = describe_measurement(measurement)
    if isinstance(criterion, GreaterThan):
        return f"Passes if {measured} is greater than {criterion.threshold:g}."
    if isinstance(criterion, EqualTo):
        return f"Passes if {measured} equals {criterion.expected:g}."
    if isinstance(criterion, IsFalse):
        return f"Passes if {measured} is false."
    return ""


class DescribedValidationTest(ABC):
    """Base for validation tests that describe the protocol they run."""

    @abstractmethod
    def describe(self, holding_current: float) -> str:
        """Describe the protocol and pass condition.

        Args:
            holding_current: Holding current in nA applied to the cell for this run.
        """


class UndescribedValidationTestError(ValueError):
    """Raised when a validation test cannot be described.

    An empty description makes the platform show its default text for the
    validation name, which may describe a different protocol than the one run.
    """


def describe_test(test: ValidationTest, holding_current: float) -> str:
    """Describe a validation test.

    The OBI-One tests describe themselves through ``DescribedValidationTest``. Other
    tests can provide a fixed ``description`` property, which is used as is.
    Otherwise parametric validations are described from their protocol and criterion.

    Args:
        test: The validation test to describe.
        holding_current: Holding current in nA applied to the cell for this run.

    Raises:
        UndescribedValidationTestError: If the test has no description and is not
            a parametric validation whose protocol and criterion can both be described.
    """
    if isinstance(test, DescribedValidationTest):
        return test.describe(holding_current)
    description = getattr(test, "description", None)
    if isinstance(description, str) and description:
        return description
    if isinstance(test, ParametricValidation):
        protocol = describe_protocol(test.protocol, holding_current)
        criterion = describe_criterion(test.measurement, test.criterion)
        if protocol and criterion:
            return f"{protocol} {criterion}"
    message = (
        f"Validation test {test.name!r} has no description. Give it a `description` "
        "property that says which protocol it runs and when it passes."
    )
    raise UndescribedValidationTestError(message)

"""Plain-text descriptions of the protocol each MEModel validation actually ran.

They are stored as ``ValidationResult.description`` so the platform can show what was
run instead of a fixed text per validation name. They are generated from the same
protocol and criterion objects the test executes, so they cannot drift from it.
"""

from bluecellulab.stimulus.factory import IDRestTimings
from bluecellulab.validation.base import ValidationTest
from bluecellulab.validation.criterion import Criterion, EqualTo, GreaterThan, IsFalse
from bluecellulab.validation.measurement import EfelMeasurement, Measurement
from bluecellulab.validation.parametric_validation import ParametricValidation
from bluecellulab.validation.protocol import Protocol, SequenceProtocol, StepProtocol

HOLDING_NOTE = "on top of the calibrated holding current"


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


def describe_location(section: str) -> str:
    """Name the injection site in words when it is the soma."""
    return "the soma" if section.startswith("soma") else section


def describe_step_protocol(protocol: StepProtocol) -> str:
    """Describe an IDRest-style step protocol."""
    amplitude = (
        format_current(protocol.amplitude)
        if protocol.amplitude is not None
        else format_rheobase_percentage(protocol.threshold_percentage)
    )
    holding = f", {HOLDING_NOTE}," if protocol.add_hypamp else ""
    return (
        f"Injects a step of {amplitude} into {describe_location(protocol.section)}{holding} "
        f"for {IDRestTimings.DURATION.value:g} ms, after {IDRestTimings.PRE_DELAY.value:g} ms "
        f"and followed by {IDRestTimings.POST_DELAY.value:g} ms."
    )


def describe_sequence_protocol(protocol: SequenceProtocol) -> str:
    """Describe a multi-phase protocol, phase by phase."""
    phases = []
    for index, (duration, amplitude) in enumerate(protocol.phases):
        value = (
            format_current(amplitude)
            if protocol.amplitude_mode == "amplitude"
            else format_rheobase_percentage(amplitude)
        )
        measured = " (measured)" if index == protocol.measurement_phase else ""
        phases.append(f"{duration:g} ms at {value}{measured}")
    text = f"Injects into {describe_location(protocol.section)}: " + ", then ".join(phases)
    if protocol.pre_delay:
        text += f", after {protocol.pre_delay:g} ms"
    if protocol.post_delay:
        text += f", followed by {protocol.post_delay:g} ms"
    text += "."
    if protocol.add_hypamp:
        text += f" Amplitudes are applied {HOLDING_NOTE}."
    else:
        text += " Amplitudes are the total injected current, including any holding."
    return text


def describe_protocol(protocol: Protocol) -> str:
    """Describe a BlueCelluLab protocol, or return "" for unknown protocol types."""
    if isinstance(protocol, StepProtocol):
        return describe_step_protocol(protocol)
    if isinstance(protocol, SequenceProtocol):
        return describe_sequence_protocol(protocol)
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


class UndescribedValidationTestError(ValueError):
    """Raised when a validation test cannot be described.

    An empty description makes the platform show its default text for the
    validation name, which may describe a different protocol than the one run.
    """


def describe_test(test: ValidationTest) -> str:
    """Describe a validation test.

    A non-empty ``description`` property is used as is; the custom OBI-One tests
    describe themselves this way. Otherwise parametric validations are described
    from their protocol and criterion.

    Raises:
        UndescribedValidationTestError: If the test has no ``description`` and is not
            a parametric validation whose protocol and criterion can both be described.
    """
    description = getattr(test, "description", None)
    if isinstance(description, str) and description:
        return description
    if isinstance(test, ParametricValidation):
        protocol = describe_protocol(test.protocol)
        criterion = describe_criterion(test.measurement, test.criterion)
        if protocol and criterion:
            return f"{protocol} {criterion}"
    message = (
        f"Validation test {test.name!r} has no description. Give it a `description` "
        "property that says which protocol it runs and when it passes."
    )
    raise UndescribedValidationTestError(message)

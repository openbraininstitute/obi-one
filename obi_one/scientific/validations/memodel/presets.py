"""OBI validation presets for MEModel entities.

Each preset returns a configured ParametricValidation instance representing
an OBI policy decision about what constitutes a valid MEModel.
"""

from bluecellulab.validation import (
    EfelMeasurement,
    GreaterThan,
    ParametricValidation,
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

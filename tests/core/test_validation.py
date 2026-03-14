"""Tests for obi_one.core.unsupported.validation module."""

from pydantic import BaseModel

from obi_one.core.unsupported.validation import (
    SingleValidationOutput,
    Validation,
)


class ConcreteValidation(Validation):
    check_name: str = "test"


class ConcreteSingleValidationOutput(SingleValidationOutput):
    extra_info: str = ""


class TestValidation:
    def test_is_base_model(self):
        assert issubclass(Validation, BaseModel)

    def test_concrete_creation(self):
        v = ConcreteValidation(check_name="morphology")
        assert v.check_name == "morphology"


class TestSingleValidationOutput:
    def test_creation(self):
        output = ConcreteSingleValidationOutput(
            name="Depolarization Block Test",
            passed=True,
            validation_details="All neurons passed.",
        )
        assert output.name == "Depolarization Block Test"
        assert output.passed is True
        assert output.validation_details == "All neurons passed."

    def test_defaults(self):
        output = ConcreteSingleValidationOutput(
            name="Test",
            passed=False,
        )
        assert not output.validation_details
        assert output.assets == []

    def test_with_assets(self):
        output = ConcreteSingleValidationOutput(
            name="Test",
            passed=True,
            assets=["/path/to/report.pdf", "/path/to/plot.png"],
        )
        assert len(output.assets) == 2

    def test_failed_validation(self):
        output = ConcreteSingleValidationOutput(
            name="Voltage Check",
            passed=False,
            validation_details="Neuron 42 showed depolarization block.",
        )
        assert output.passed is False
        assert "Neuron 42" in output.validation_details

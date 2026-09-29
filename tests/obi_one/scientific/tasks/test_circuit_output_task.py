from unittest.mock import Mock

import pytest

from obi_one.db_sdk.registration.circuit.lifecycle import CircuitValidationMode
from obi_one.scientific.tasks.circuit_output_task import CircuitOutputTask


class _Task(CircuitOutputTask):
    config: int = 0
    circuit_validation_mode: CircuitValidationMode = CircuitValidationMode.skip

    def execute(self, **kwargs) -> None:
        pass


class TestCircuitOutputTask:
    @pytest.mark.parametrize(
        ("validation_mode", "defer"),
        [
            (CircuitValidationMode.async_launch, True),
            (CircuitValidationMode.sync_bluepysnap, False),
            (CircuitValidationMode.sync_neurodamus, False),
            (CircuitValidationMode.skip, False),
        ],
    )
    def test_assets_are_deferred_only_for_async_launch(self, validation_mode, defer):
        assert _Task(circuit_validation_mode=validation_mode)._defer_circuit_assets is defer

    def test_task_option_value_is_coerced_to_the_enum(self):
        """The launch script passes the option as a string (``--task_option KEY=VALUE``)."""
        task = _Task(circuit_validation_mode="async_launch")

        assert task.circuit_validation_mode is CircuitValidationMode.async_launch

    @pytest.mark.parametrize(
        ("validation_mode", "execution_activity"),
        [
            (CircuitValidationMode.async_launch, Mock()),
            (CircuitValidationMode.sync_bluepysnap, None),
            (CircuitValidationMode.skip, None),
        ],
    )
    def test_check_accepts(self, validation_mode, execution_activity):
        _Task(circuit_validation_mode=validation_mode)._check_circuit_validation_mode(
            execution_activity
        )

    def test_check_rejects_async_launch_without_activity(self):
        """A draft without an execution activity would never be validated."""
        task = _Task(circuit_validation_mode=CircuitValidationMode.async_launch)

        with pytest.raises(ValueError, match="requires an execution activity"):
            task._check_circuit_validation_mode(None)

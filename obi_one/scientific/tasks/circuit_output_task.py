"""Base class for tasks that register a circuit."""

from entitysdk.models import TaskActivity

from obi_one.core.task import Task
from obi_one.db_sdk.registration.circuit.lifecycle import CircuitValidationMode


class CircuitOutputTask(Task):
    """A task that registers a circuit and validates it as ``circuit_validation_mode`` says.

    Each subclass sets the field's default, which is what local runs use. When the API launches
    the task, the job gets ``circuit_validation_mode=async_launch`` (see
    ``app.services.generated_entities``): the task registers the circuit as a draft, and a
    launch-system job validates it after the task succeeds.
    """

    circuit_validation_mode: CircuitValidationMode

    def _check_circuit_validation_mode(self, execution_activity: TaskActivity | None) -> None:
        """Fail early when ``async_launch`` is used without an execution activity.

        The validation job is started for the draft circuits listed in the activity. With no
        activity, the draft would never be validated.
        """
        if (
            self.circuit_validation_mode == CircuitValidationMode.async_launch
            and execution_activity is None
        ):
            msg = (
                "Circuit validation mode 'async_launch' requires an execution activity: its "
                "draft circuits are validated through it."
            )
            raise ValueError(msg)

    @property
    def _defer_circuit_assets(self) -> bool:
        """True when the extra assets are left to the asset job that runs after validation."""
        return self.circuit_validation_mode == CircuitValidationMode.async_launch

from enum import StrEnum, auto


class TaskType(StrEnum):
    """Task types supported for job submission."""

    circuit_extraction = auto()
    circuit_simulation = auto()


class CallBackEvent(StrEnum):
    job_on_failure = auto()
    job_on_success = auto()
    job_on_cancellation = auto()


class CallBackAction(StrEnum):
    http_request = auto()
    http_request_with_token = auto()

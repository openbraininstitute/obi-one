from enum import StrEnum, auto

# re-export from obi-one so that obi_one is not
# imported everywhere
from obi_one.types import TaskType as TaskType  # noqa: PLC0414


class CallBackEvent(StrEnum):
    job_on_failure = auto()
    job_on_success = auto()
    job_on_cancellation = auto()


class CallBackAction(StrEnum):
    http_request = auto()
    http_request_with_token = auto()


class ResourcesConfigType(StrEnum):
    """Resources configuration type."""

    machine = auto()
    cluster = auto()


class CodeType(StrEnum):
    """Code type."""

    python_repository = auto()
    builtin = auto()


class BuiltinScript(StrEnum):
    """Builtin script."""

    circuit_simulation = auto()

"""Config validation service.

Runs the same execution flow as the /generated/* endpoints but with write
operations intercepted, allowing semantic validation without creating resources.
"""

import tempfile
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import entitysdk

from obi_one.core.run_tasks import run_tasks_for_generated_scan
from obi_one.core.scan_config import ScanConfig
from obi_one.core.scan_generation import GridScanGenerationTask


class _WriteInterceptingClient:
    """A wrapper around entitysdk.client.Client that intercepts write operations.

    Read operations are delegated to the real client.
    Write operations (register_entity, upload_file, update_entity) return mocks.
    Thread-safe because each validation gets its own wrapper instance.
    """

    def __init__(self, real_client: entitysdk.client.Client) -> None:
        self._real_client = real_client
        self.register_call_count = 0
        self.upload_call_count = 0
        self.update_call_count = 0

    def register_entity(self, entity: Any) -> MagicMock:
        self.register_call_count += 1
        if isinstance(entity, entitysdk.models.Simulation):  # ty:ignore[possibly-missing-submodule]
            mock = MagicMock(spec=entitysdk.models.Simulation)  # ty:ignore[possibly-missing-submodule]
            mock.id = uuid4()
            return mock
        mock = MagicMock(spec=["id"])
        mock.id = uuid4()
        return mock

    def upload_file(self, *args: Any, **kwargs: Any) -> None:  # noqa: ARG002
        self.upload_call_count += 1

    def update_entity(self, *args: Any, **kwargs: Any) -> None:  # noqa: ARG002
        self.update_call_count += 1

    def __getattr__(self, name: str) -> Any:
        """Delegate all other attribute access (reads) to the real client."""
        return getattr(self._real_client, name)


def run_grid_scan_validation(
    config: ScanConfig,
    db_client: entitysdk.client.Client,
    *,
    execute_single_config_task: bool,
) -> str | None:
    """Run the standard grid scan validation flow.

    This mirrors what the /generated/* endpoints do:
    1. GridScanGenerationTask.execute() — always
    2. run_tasks_for_generated_scan() — only if execute_single_config_task=True

    Returns an error string or None if valid.
    """
    try:
        mock_client = _WriteInterceptingClient(db_client)

        with tempfile.TemporaryDirectory() as tdir:
            grid_scan = GridScanGenerationTask(
                form=config,  # ty:ignore[invalid-argument-type]
                output_root=tdir,  # ty:ignore[invalid-argument-type]
                coordinate_directory_option="ZERO_INDEX",
            )
            grid_scan.execute(db_client=mock_client)  # ty:ignore[invalid-argument-type]

            if execute_single_config_task:
                run_tasks_for_generated_scan(grid_scan, db_client=mock_client, entity_cache=True)  # ty:ignore[invalid-argument-type]

        # Sanity check: register_entity and upload_file must have been called
        if mock_client.register_call_count == 0 or mock_client.upload_call_count == 0:
            return (
                "Validation error: Expected database operations did not occur. "
                "The validation logic may be outdated."
            )

        # If tasks were executed, update_entity should also have been called
        if execute_single_config_task and mock_client.update_call_count == 0:
            return (
                "Validation error: Expected update operations did not occur. "
                "The validation logic may be outdated."
            )
    except Exception as e:  # noqa: BLE001
        return str(e)

    return None

"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports, import-private-name]

from obi_one_lazy.db_sdk.registration.simulation_result.register import (
    AssetLabel,
    Client,
    ContentType,
    EXTENSION_TO_CONTENT_TYPE,
    L,
    logging,
    models,
    Path,
    register_simulation_results,
    Sequence,
    UUID,
)

from obi_one_lazy.db_sdk.registration.simulation_result.register import (
    _upload_report,
)

__all__ = [
    "AssetLabel",
    "Client",
    "ContentType",
    "EXTENSION_TO_CONTENT_TYPE",
    "L",
    "logging",
    "models",
    "Path",
    "register_simulation_results",
    "Sequence",
    "UUID",
    "_upload_report",
]

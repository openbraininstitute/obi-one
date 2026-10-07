"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports, import-private-name]

from obi_one_lazy.scientific.from_id.em_dataset_from_id import (
    Callable,
    CAVEclient,
    ClassVar,
    Client,
    EMDataSetFromID,
    EMDenseReconstructionDataset,
    Entity,
    EntityFromID,
    functools,
    numpy,
    OBIONEError,
    pandas,
    PrivateAttr,
    requests,
    set_session_defaults,
    settings,
    SYNAPSE_POSITION_COLUMNS,
)

from obi_one_lazy.scientific.from_id.em_dataset_from_id import (
    _configure_caveclient_retries,
    _graceful_materialize_errors,
    _NM_to_UM,
)

__all__ = [
    "Callable",
    "CAVEclient",
    "ClassVar",
    "Client",
    "EMDataSetFromID",
    "EMDenseReconstructionDataset",
    "Entity",
    "EntityFromID",
    "functools",
    "numpy",
    "OBIONEError",
    "pandas",
    "PrivateAttr",
    "requests",
    "set_session_defaults",
    "settings",
    "SYNAPSE_POSITION_COLUMNS",
    "_configure_caveclient_retries",
    "_graceful_materialize_errors",
    "_NM_to_UM",
]

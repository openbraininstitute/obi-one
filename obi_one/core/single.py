"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import]

from obi_one_lazy.core.single import (
    Any,
    Block,
    Client,
    COORDINATE_CONFIG_FILENAME,
    db_sdk,
    Entity,
    Field,
    field_validator,
    json,
    L,
    logging,
    OBIBaseModel,
    OrderedDict,
    Path,
    SingleConfigMixin,
    SingleCoordinateScanParams,
    SingleValueScanParam,
    task_registry,
    TaskConfig,
    TaskConfigType,
    version,
)

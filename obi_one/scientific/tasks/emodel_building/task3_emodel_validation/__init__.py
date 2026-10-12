"""Task 3 e-model validation package.

Like Task 2, Task 3 requires the optional ``emodel`` dependency group (``bluepyemodel``).
This module is the single place that guards the import; when ``bluepyemodel`` is not
installed, the names below are ``None`` and ``HAS_EMODEL_VALIDATION`` is ``False``.
"""

from obi_one.core.scan_config import ScanConfig

try:  # ruff: ignore[non-empty-init-module]
    from obi_one.scientific.tasks.emodel_building.task3_emodel_validation.config import (
        EModelValidationScanConfig,
        EModelValidationSingleConfig,
    )
    from obi_one.scientific.tasks.emodel_building.task3_emodel_validation.task import (
        EModelValidationTask,
    )

    HAS_EMODEL_VALIDATION = True
except ImportError:
    EModelValidationScanConfig: type[ScanConfig] | None = None
    EModelValidationSingleConfig: type[ScanConfig] | None = None
    EModelValidationTask: type | None = None

    HAS_EMODEL_VALIDATION = False

__all__ = [
    "HAS_EMODEL_VALIDATION",
    "EModelValidationScanConfig",
    "EModelValidationSingleConfig",
    "EModelValidationTask",
]

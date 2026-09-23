"""Task 2 e-model optimization package.

Task 2 requires the optional ``emodel`` dependency group (``bluepyemodel``). This
module is the single place that guards the import: consumers elsewhere in the
codebase (``obi_one/__init__.py``, ``config_task_map.py``,
``unions_and_references/scan_configs.py``, ``unions_and_references/tasks.py``)
import from here directly instead of each repeating their own
``try/except ImportError``. When ``bluepyemodel`` is not installed, the names
below are ``None`` and ``HAS_EMODEL_OPTIMIZATION`` is ``False``.
"""

try:  # ruff: ignore[non-empty-init-module]
    from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.blocks import (
        CustomDistanceDependentDistribution,
        DistanceDependentDistribution,
        ExponentialDistanceDependentDistribution,
        ExponentialNaDendDistanceDependentDistribution,
        LinearEPasApicDistanceDependentDistribution,
        LinearHDApicDistanceDependentDistribution,
        LinearHDPasDistanceDependentDistribution,
        SigmoidKADApicDistanceDependentDistribution,
        SigmoidKADDistanceDependentDistribution,
        SigmoidKDBMApicDistanceDependentDistribution,
        StepDistanceDependentDistribution,
        UniformDistanceDependentDistribution,
    )
    from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.config import (
        EModelOptimizationScanConfig,
        EModelOptimizationSingleConfig,
    )
    from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.task import (
        EModelOptimizationTask,
    )

    HAS_EMODEL_OPTIMIZATION = True
except ImportError:
    CustomDistanceDependentDistribution: type | None = None
    DistanceDependentDistribution: type | None = None
    ExponentialDistanceDependentDistribution: type | None = None
    ExponentialNaDendDistanceDependentDistribution: type | None = None
    LinearEPasApicDistanceDependentDistribution: type | None = None
    LinearHDApicDistanceDependentDistribution: type | None = None
    LinearHDPasDistanceDependentDistribution: type | None = None
    SigmoidKADApicDistanceDependentDistribution: type | None = None
    SigmoidKADDistanceDependentDistribution: type | None = None
    SigmoidKDBMApicDistanceDependentDistribution: type | None = None
    StepDistanceDependentDistribution: type | None = None
    UniformDistanceDependentDistribution: type | None = None
    EModelOptimizationScanConfig: type | None = None
    EModelOptimizationSingleConfig: type | None = None
    EModelOptimizationTask: type | None = None

    HAS_EMODEL_OPTIMIZATION = False

__all__ = [
    "HAS_EMODEL_OPTIMIZATION",
    "CustomDistanceDependentDistribution",
    "DistanceDependentDistribution",
    "EModelOptimizationScanConfig",
    "EModelOptimizationSingleConfig",
    "EModelOptimizationTask",
    "ExponentialDistanceDependentDistribution",
    "ExponentialNaDendDistanceDependentDistribution",
    "LinearEPasApicDistanceDependentDistribution",
    "LinearHDApicDistanceDependentDistribution",
    "LinearHDPasDistanceDependentDistribution",
    "SigmoidKADApicDistanceDependentDistribution",
    "SigmoidKADDistanceDependentDistribution",
    "SigmoidKDBMApicDistanceDependentDistribution",
    "StepDistanceDependentDistribution",
    "UniformDistanceDependentDistribution",
]

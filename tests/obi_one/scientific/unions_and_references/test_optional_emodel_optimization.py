"""Cover the ``bluepyemodel``-absent fallback branches in the library.

Task 2 (emodel optimization) requires the optional ``emodel`` extra
(``bluepyemodel``). Importing ``obi_one`` must still succeed when that extra is
not installed: the single guard lives in
``task2_emodel_optimization/__init__.py`` (``try/except ImportError`` around the
Task 2 imports, exposing ``None`` placeholders and ``HAS_EMODEL_OPTIMIZATION``).
``config_task_map.py``, ``scan_configs.py``, and ``tasks.py`` declare Task 2 by class path
and gate it on ``requires_package="bluepyemodel"``, so they never import Task 2 at module
import time and report the task type as unavailable when the extra is missing.

These tests simulate ``bluepyemodel`` being absent by re-executing each module's real
source with a blocking meta path finder, so the ``except`` branches run for real instead
of being mocked. Matching app-endpoint coverage lives in
``tests/app/test_optional_emodel_optimization.py``.
"""

import importlib
import importlib.util
import sys
import types
from collections.abc import Iterator

import pytest


class _BlockBluePyEModel(importlib.abc.MetaPathFinder):
    """Meta path finder that makes ``bluepyemodel`` (and submodules) unimportable."""

    def find_spec(self, fullname, path=None, target=None):  # ruff: ignore[unused-method-argument]
        if fullname == "bluepyemodel" or fullname.startswith("bluepyemodel."):
            msg = f"No module named {fullname!r} (blocked for test)"
            raise ImportError(msg)


# Only these modules are evicted from ``sys.modules`` before re-executing, so a fresh
# execution actually re-runs their top-level ``try/except ImportError`` instead of
# returning the already-cached module (which still holds the resolved Task 2 classes).
# Deliberately narrow: never touches ``obi_one`` itself or unrelated third-party
# packages, to avoid corrupting state for other tests in the same process.
_MODULES_TO_EVICT = (
    "bluepyemodel",
    "obi_one.scientific.tasks.emodel_building.task2_emodel_optimization",
    "obi_one.scientific.tasks.emodel_building.task3_emodel_validation",
    "obi_one.scientific.mappings_and_registry.config_task_map",
)


@pytest.fixture
def bluepyemodel_blocked() -> Iterator[None]:
    """Block ``bluepyemodel`` imports and evict cached modules for the duration of the test."""
    blocker = _BlockBluePyEModel()
    original_modules = {
        name: module
        for name, module in sys.modules.items()
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in _MODULES_TO_EVICT)
    }
    for name in original_modules:
        del sys.modules[name]

    sys.meta_path.insert(0, blocker)
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)
        for name in list(sys.modules):
            if any(name == prefix or name.startswith(f"{prefix}.") for prefix in _MODULES_TO_EVICT):
                del sys.modules[name]
        sys.modules.update(original_modules)


def _exec_fresh(module_name: str) -> types.ModuleType:
    """Re-execute a module's real source from scratch, bypassing the import cache.

    ``importlib.reload`` is not enough here: the already-imported module object
    still holds references to the previously resolved Task 2 classes. Building a
    brand new module from the same spec and executing it exercises the module's
    top-level ``try/except ImportError`` for real. The freshly built module is
    never installed into ``sys.modules``, so it cannot be picked up by anything
    else importing ``module_name`` afterwards.
    """
    spec = importlib.util.find_spec(module_name)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.usefixtures("bluepyemodel_blocked")
def test_task2_package_omits_emodel_optimization_without_bluepyemodel():
    module = _exec_fresh("obi_one.scientific.tasks.emodel_building.task2_emodel_optimization")

    assert module.HAS_EMODEL_OPTIMIZATION is False
    assert module.EModelOptimizationScanConfig is None
    assert module.EModelOptimizationSingleConfig is None
    assert module.EModelOptimizationTask is None
    assert module.DistanceDependentDistribution is None


@pytest.mark.usefixtures("bluepyemodel_blocked")
def test_scan_configs_union_omits_emodel_optimization_without_bluepyemodel():
    module = _exec_fresh("obi_one.scientific.unions_and_references.scan_configs")

    assert "EModelOptimizationScanConfig" not in {
        member.__name__ for member in module._SCAN_CONFIG_MEMBERS
    }


@pytest.mark.usefixtures("bluepyemodel_blocked")
def test_tasks_union_omits_emodel_optimization_without_bluepyemodel():
    module = _exec_fresh("obi_one.scientific.unions_and_references.tasks")

    assert "EModelOptimizationTask" not in {member.__name__ for member in module._TASK_MEMBERS}


@pytest.mark.usefixtures("bluepyemodel_blocked")
def test_config_task_map_omits_emodel_optimization_without_bluepyemodel():
    module = _exec_fresh("obi_one.scientific.mappings_and_registry.config_task_map")

    assert module._is_task_type_available(module.TaskType.emodel_optimization) is False
    with pytest.raises(KeyError, match="emodel_optimization"):
        module.get_task_spec_for_task_type(module.TaskType.emodel_optimization)


@pytest.mark.usefixtures("bluepyemodel_blocked")
def test_unions_omit_emodel_validation_without_bluepyemodel():
    scan_configs = _exec_fresh("obi_one.scientific.unions_and_references.scan_configs")
    tasks = _exec_fresh("obi_one.scientific.unions_and_references.tasks")
    assert "EModelValidationScanConfig" not in {
        m.__name__ for m in scan_configs._SCAN_CONFIG_MEMBERS
    }
    assert "EModelValidationTask" not in {m.__name__ for m in tasks._TASK_MEMBERS}

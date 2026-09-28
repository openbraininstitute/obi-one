"""Cover the ``bluepyemodel``-absent fallback branches.

Task 2 (emodel optimization) requires the optional ``emodel`` extra
(``bluepyemodel``). Importing ``obi_one`` must still succeed when that extra is
not installed: the single guard lives in
``task2_emodel_optimization/__init__.py`` (``try/except ImportError`` around the
Task 2 imports, exposing ``None`` placeholders and ``HAS_EMODEL_OPTIMIZATION``).
``scan_configs.py``, ``tasks.py``, and ``config_task_map.py`` import from that
package unconditionally and simply omit Task 2 when the classes are ``None``.
The same applies to ``app/endpoints/ion_channel_properties.py`` and
``app/endpoints/scan_config.py``, which import ``fetch_variable_catalog`` and
``EModelOptimizationScanConfig`` respectively and are both pulled in by
``app.application`` at import time; ``import app.application`` (i.e. starting
the FastAPI service) must succeed without ``bluepyemodel`` too. These tests
simulate ``bluepyemodel`` being absent by re-executing each module's real
source with a blocking meta path finder, so the ``except`` branches run for
real instead of being mocked. Only these two ``app.endpoints`` modules are
covered directly (not ``app.application`` itself); see the comment below the
tests for why.

Only the ``bluepyemodel``, Task 2, and affected ``app`` modules are evicted
from ``sys.modules`` (never ``obi_one``/``app`` themselves in their entirety,
or unrelated third-party packages), and the original entries are always
restored, so this cannot leak state into other tests.
"""

import importlib
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
    "app.endpoints.ion_channel_properties",
    "app.endpoints.scan_config",
    "app.application",
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

    assert module.EModelOptimizationScanConfig is None
    assert "EModelOptimizationScanConfig" not in {
        member.__name__ for member in module._SCAN_CONFIG_MEMBERS
    }


@pytest.mark.usefixtures("bluepyemodel_blocked")
def test_tasks_union_omits_emodel_optimization_without_bluepyemodel():
    module = _exec_fresh("obi_one.scientific.unions_and_references.tasks")

    assert module.EModelOptimizationTask is None
    assert "EModelOptimizationTask" not in {member.__name__ for member in module._TASK_MEMBERS}


@pytest.mark.usefixtures("bluepyemodel_blocked")
def test_config_task_map_omits_emodel_optimization_without_bluepyemodel():
    module = _exec_fresh("obi_one.scientific.mappings_and_registry.config_task_map")

    assert module.HAS_EMODEL_OPTIMIZATION is False
    assert module.TaskType.emodel_optimization not in module.TASK_MAP


@pytest.mark.usefixtures("bluepyemodel_blocked")
def test_ion_channel_properties_endpoint_module_omits_variable_catalog_without_bluepyemodel():
    module = _exec_fresh("app.endpoints.ion_channel_properties")

    assert module.fetch_variable_catalog is None


@pytest.mark.usefixtures("bluepyemodel_blocked")
def test_scan_config_endpoint_module_omits_emodel_optimization_without_bluepyemodel():
    module = _exec_fresh("app.endpoints.scan_config")

    assert module.EModelOptimizationScanConfig is None


# Deliberately no test re-imports `app.application` itself here. Unlike the narrower
# modules above, `app.application` transitively pulls in many other `obi_one` modules
# (e.g. `count_scan_coordinates.py` -> `unions_and_references/scan_configs.py`) that are
# *not* in `_MODULES_TO_EVICT` and were already fully imported with `bluepyemodel` present
# earlier in the test session (e.g. via `tests/conftest.py`). Re-importing `app.application`
# in that state races against those already-cached modules and can non-deterministically
# resolve the "fresh" `app.endpoints.scan_config` import back to the pre-eviction
# `EModelOptimizationScanConfig` class, producing a false negative (or false positive)
# depending on test run order. This was confirmed by direct experimentation: the same
# reimport is reliable in a pristine interpreter that has never imported `bluepyemodel`,
# but flaky inside a shared pytest session. `test_ion_channel_properties_endpoint_module_
# omits_variable_catalog_without_bluepyemodel` and `test_scan_config_endpoint_module_omits_
# emodel_optimization_without_bluepyemodel` above already cover the two files directly
# responsible for the real bug (unconditional Task 2 imports in app/endpoints/), which is
# what actually matters for `import app.application` to succeed without bluepyemodel.

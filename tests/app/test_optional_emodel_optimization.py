"""Cover ``bluepyemodel``-absent fallback branches in app endpoints.

See ``tests/obi_one/scientific/unions_and_references/test_optional_emodel_optimization.py``
for the matching library-side coverage.
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


_MODULES_TO_EVICT = (
    "bluepyemodel",
    "obi_one.scientific.tasks.emodel_building.task2_emodel_optimization",
    "obi_one.scientific.tasks.emodel_building.task3_emodel_validation",
    "app.endpoints.ion_channel_properties",
    "app.endpoints.scan_config",
    "app.endpoints.config_validation",
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
    """Re-execute a module's real source from scratch, bypassing the import cache."""
    spec = importlib.util.find_spec(module_name)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.usefixtures("bluepyemodel_blocked")
def test_ion_channel_properties_endpoint_module_omits_variable_catalog_without_bluepyemodel():
    module = _exec_fresh("app.endpoints.ion_channel_properties")

    assert module.fetch_variable_catalog is None


@pytest.mark.usefixtures("bluepyemodel_blocked")
def test_scan_config_endpoint_module_omits_emodel_optimization_without_bluepyemodel():
    module = _exec_fresh("app.endpoints.scan_config")

    assert module.EModelOptimizationScanConfig is None


@pytest.mark.usefixtures("bluepyemodel_blocked")
def test_config_validation_omits_emodel_optimization_without_bluepyemodel():
    """The shared-state model must drop the key rather than fail to import."""
    module = _exec_fresh("app.endpoints.config_validation")

    assert "emodel_optimization_config" not in module.SharedStatePartial.model_fields
    assert set(module.SharedStatePartial.model_fields) == set(module._VALIDATION_CONFIG)

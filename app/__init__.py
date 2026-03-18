"""FastAPI service for OBI-ONE.

This module provides the REST API service for OBI-ONE, including endpoints
for circuit analysis, morphology validation, task execution, and more.

Requires: make install-service
"""

import importlib.metadata

# Check for service dependencies with minimum versions
# This ensures the [service] extra was properly installed
_REQUIRED_DEPS = {
    "fastapi": ("fastapi", None),
    "uvicorn": ("uvicorn", None),
    "starlette": ("starlette", None),
    "pydantic_settings": ("pydantic-settings", "2.8.1"),
    "pydantic_core": ("pydantic-core", None),
    "jwt": ("pyjwt", "2.10.1"),
    "cachetools": ("cachetools", "5.5.2"),
    "httpx": ("httpx", "0.28.1"),
    "obp_accounting_sdk": ("obp-accounting-sdk", "0.5.0"),
}

_MISSING_DEPS = []
_OUTDATED_DEPS = []


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Parse version string into tuple of integers for comparison."""
    return tuple(int(x) for x in version_str.split(".")[:3])  # Major.Minor.Patch


for module_name, (package_name, min_version) in _REQUIRED_DEPS.items():
    try:
        __import__(module_name)
        # Check version if minimum is specified
        if min_version:
            try:
                installed_version = importlib.metadata.version(package_name)
                if _parse_version(installed_version) < _parse_version(min_version):
                    _OUTDATED_DEPS.append(
                        f"{package_name} (installed: {installed_version}, required: >={min_version})"
                    )
            except Exception:  # noqa: S110
                # If we can't check version, just continue
                pass
    except ImportError:
        _MISSING_DEPS.append(package_name)

error_msg = []
if _MISSING_DEPS:
    error_msg.append(
            f"Missing {len(_MISSING_DEPS)} package(s): {', '.join(_MISSING_DEPS)}"
        )

if _OUTDATED_DEPS:
    error_msg.append(
        f"Outdated {len(_OUTDATED_DEPS)} package(s): {', '.join(_OUTDATED_DEPS)}"
    )

if error_msg:
    raise ImportError(
        f"Service dependencies not satisfied. {'. '.join(error_msg)}. "
        "Install with: make install-service"
    )

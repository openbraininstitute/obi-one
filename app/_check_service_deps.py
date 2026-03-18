"""Check that service dependencies are installed.

This module runs the check at import time.
"""

_SERVICE_MODULES = [
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("starlette", "starlette"),
    ("pydantic_settings", "pydantic-settings"),
    ("pydantic_core", "pydantic-core"),
    ("jwt", "pyjwt"),
    ("cachetools", "cachetools"),
    ("httpx", "httpx"),
    ("obp_accounting_sdk", "obp-accounting-sdk"),
]

_missing = []
for _module_name, _package_name in _SERVICE_MODULES:
    try:
        __import__(_module_name)
    except ImportError:
        _missing.append(_package_name)

if _missing:
    _msg = (
        f"Service dependencies not satisfied. "
        f"Missing {len(_missing)} package(s): {', '.join(_missing)}. "
        f"Install with: pip install obi-one[service]"
    )
    raise ImportError(_msg)

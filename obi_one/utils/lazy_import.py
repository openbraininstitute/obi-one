"""Defer imports until first use.

Declaring a class by reference instead of importing it lets registries be plain data:
the module holding the class is imported only when the class itself is needed.
``import_optional`` does the same for modules of optional dependencies, so code using them
imports without the extra and fails only when the feature is used.
"""

from functools import cache
from importlib import import_module
from types import ModuleType

type ClassRef = tuple[str, str]
"""A reference to a class as ``(module path, class name)``."""


def class_name(class_ref: ClassRef) -> str:
    """Return the class name of ``class_ref`` without importing it."""
    return class_ref[1]


def module_name(class_ref: ClassRef) -> str:
    """Return the module path of ``class_ref`` without importing it."""
    return class_ref[0]


@cache
def import_class(class_ref: ClassRef) -> type:
    """Import and return the class named by ``class_ref``.

    Results are cached, so repeated lookups of the same reference are free.
    """
    module, name = class_ref
    return getattr(import_module(module), name)


def import_optional(module: str, *, extra: str) -> ModuleType:
    """Import ``module`` from an optional dependency of the obi-one ``extra``.

    Raises:
        ImportError: If the module is missing, naming the extra that provides it.
    """
    try:
        return import_module(module)
    except ImportError as err:
        package = module.split(".", maxsplit=1)[0]
        msg = (
            f"This feature requires '{package}', which is not installed. "
            f"Install with: pip install 'obi-one[{extra}]'"
        )
        raise ImportError(msg) from err

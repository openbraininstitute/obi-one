"""Resolve ``(module path, class name)`` references to classes on first use.

Declaring a class by reference instead of importing it lets registries be plain data:
the module holding the class is imported only when the class itself is needed.
"""

from functools import cache
from importlib import import_module

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

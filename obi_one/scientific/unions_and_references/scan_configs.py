from functools import reduce
from operator import or_
from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.mappings_and_registry.config_task_map import iter_scan_config_refs
from obi_one.utils.lazy_import import import_class

_SCAN_CONFIG_MEMBERS: tuple[type, ...] = tuple(
    import_class(class_ref) for class_ref in iter_scan_config_refs()
)

ScanConfigsUnion = Annotated[
    reduce(or_, _SCAN_CONFIG_MEMBERS),  # ty: ignore[invalid-type-form]
    Discriminator("type"),
]

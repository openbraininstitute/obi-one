from typing import Any, ClassVar, get_args

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.simplification_algorithms import SimplificationAlgorithmUnion


class SimplificationAlgorithmReference(BlockReference):
    """A reference to a circuit-simplification algorithm block."""

    allowed_block_types: ClassVar[Any] = SimplificationAlgorithmUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(
            get_args(SimplificationAlgorithmUnion)[0]
        )
    }


SIMPLIFICATION_ALGORITHM_REFERENCE_TYPES = [SimplificationAlgorithmReference.__name__]

__all__ = [
    "SIMPLIFICATION_ALGORITHM_REFERENCE_TYPES",
    "SimplificationAlgorithmReference",
]

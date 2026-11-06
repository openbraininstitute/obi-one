from typing import Annotated, Any, ClassVar, cast

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.structural_conn_models.base import PathwayStructuralConnModel
from obi_one.scientific.blocks.structural_conn_models.distance_dependent import (
    DistanceDependentConnModel,
)
from obi_one.scientific.blocks.structural_conn_models.erdos_renyi import ErdosRenyiConnModel
from obi_one.scientific.blocks.structural_conn_models.sgsg import SgsgConnModel

STRUCTURAL_CONN_MODELS = ErdosRenyiConnModel | DistanceDependentConnModel | SgsgConnModel

StructuralConnModelUnion = Annotated[
    STRUCTURAL_CONN_MODELS,
    Discriminator("type"),
]


class PathwayStructuralConnModelReference(BlockReference):
    """A reference to a PathwayStructuralConnModel block."""

    allowed_block_types: ClassVar[Any] = StructuralConnModelUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(STRUCTURAL_CONN_MODELS)
    }

    @property
    def block(self) -> PathwayStructuralConnModel:
        """The block associated with this reference."""
        if isinstance(super().block, PathwayStructuralConnModel):
            return cast("PathwayStructuralConnModel", super().block)
        msg = f"Expected block of type PathwayStructuralConnModel, but got {type(super().block)}"
        raise TypeError(msg)

    @block.setter
    def block(self, value: PathwayStructuralConnModel) -> None:
        BlockReference.block.fset(self, value)


STRUCTURAL_CONN_MODELS_REFERENCE_TYPES = BlockReference.get_class_names(
    PathwayStructuralConnModelReference
)

__all__ = [
    "STRUCTURAL_CONN_MODELS_REFERENCE_TYPES",
    "PathwayStructuralConnModelReference",
    "StructuralConnModelUnion",
]

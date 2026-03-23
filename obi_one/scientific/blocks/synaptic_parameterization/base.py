from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement


class SynapseParameterization(Block):
    overwrite_if_exists: bool = Field(
        title="Overwrite",
        description="Overwrite if a parameterization exists already.",
        default=False,
    )

    random_seed: int = Field(
        default=1,
        title="Random seed",
        description="Seed for drawing random values from physiological parameter distributions.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INTEGER,
        },
    )

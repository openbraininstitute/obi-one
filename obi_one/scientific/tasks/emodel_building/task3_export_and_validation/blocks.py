"""Blocks for the 03_export_and_validation stage.

Validates the draft EModel/MEModel from the optimisation stage and promotes
them to active lifecycle status. All validation/plotting settings come from
the optimisation recipe (stored on the TaskResult).
"""

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID


class ExportAndValidationInitialize(Block):
    """Entity-based inputs for the export + validation stage."""

    optimization_task_result: TaskResultFromID = Field(
        title="Optimization TaskResult",
        description=(
            "TaskResult entity from the 02_emodel_optimization stage."
            " The recipe (with validation_protocols, plotting settings, etc.),"
            " checkpoint, and all assets are read from this entity."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER},
    )

    memodel: MEModelFromID = Field(
        title="MEModel to validate",
        description=(
            "Draft MEModel entity registered by the optimisation stage."
            " On successful validation, this entity (and its linked EModel)"
            " will be promoted from draft to active lifecycle status."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER},
    )

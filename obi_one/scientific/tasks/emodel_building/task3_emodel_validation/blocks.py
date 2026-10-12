"""Blocks for the Task 3 e-model validation stage."""

from typing import Literal

from entitysdk.types import EntityType, TaskResultType
from pydantic import Field, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.from_id.emodel_from_id import EModelFromID
from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID

FROM_OPTIMISATION = "from_optimisation"


class EModelInput(Block):
    """Optimised e-model to validate (Inputs card)."""

    emodel: EModelFromID = Field(
        title="E-model",
        description=(
            "EModel registered by the E-model optimisation workflow. Its optimisation "
            "configuration, parameters and exemplar morphology are resolved through "
            "provenance."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.MODEL_SELECTOR_SINGLE,
            SchemaKey.ENTITY_QUERY: {"type": EntityType.emodel},
        },
    )


class ValidationTargetEFeaturesInput(Block):
    """E-features the e-model is scored against (Inputs card)."""

    task_result: TaskResultFromID = Field(
        title="Target e-features",
        description=(
            "E-feature extraction TaskResult. Defaults to the e-model's optimisation "
            "targets; another (e.g. fresh) extraction can be selected instead."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.TASK_RESULT_SELECTOR,
            SchemaKey.TASK_RESULT_TYPE: TaskResultType.efeature_extraction__result,
        },
    )


class ValidationSettings(Block):
    """Protocols and scoring used to decide whether the e-model passes validation."""

    validation_protocols: list[str] | None = Field(
        default=None,
        title="Validation protocols",
        description=(
            "Protocol names (e.g. ``IDrest_250``) scored as validation protocols. Empty uses "
            "the optimisation's validation protocols for optimisation targets, and every "
            "protocol of the extraction for e-feature extraction targets."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_LIST_OPTIONAL},
    )
    validation_protocols_only: bool = Field(
        default=False,
        title="Validation protocols only",
        description=(
            "Aggregate only the validation-protocol scores for the overall verdict. When off, "
            "all scored protocols are aggregated (BluePyEModel default)."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    validation_function: Literal["from_optimisation", "max_score", "mean_score"] = Field(
        default=FROM_OPTIMISATION,
        title="Score aggregation",
        description=(
            "``max_score`` compares the worst e-feature score, ``mean_score`` the mean score, "
            "to the threshold. ``from_optimisation`` reuses the optimisation setting."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    validation_threshold: PositiveFloat | None = Field(
        default=None,
        title="Score threshold",
        description=(
            "Aggregated score (in standard deviations) below which validation passes. "
            "Empty reuses the optimisation setting."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL},
    )

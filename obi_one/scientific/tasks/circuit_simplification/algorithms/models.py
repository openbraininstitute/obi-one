from typing import Annotated, Any, ClassVar, Literal

from pydantic import ConfigDict, Discriminator, Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.tasks.circuit_simplification.algorithms.base import SimplificationAlgorithm
from obi_one.scientific.tasks.circuit_simplification.algorithms.metadata import (
    ALGORITHM_EXPORT_DESCRIPTIONS,
    ALGORITHM_EXPORT_TITLES,
)

# sonata_simplify fits 1-4 poles; 1 and 2 map to dedicated ProbFilt mods, 3-4 use the
# zero-padded ProbFilt5 mods.
MAX_FILTER_POLES = 4
FilterPoles = Annotated[int, Field(ge=1, le=MAX_FILTER_POLES)]


class SingleCompartmentAlgorithm(SimplificationAlgorithm):
    title: ClassVar[str] = ALGORITHM_EXPORT_TITLES["single_compartment"]
    algorithm_name: ClassVar[str] = "single_compartment"
    model_config = ConfigDict(
        json_schema_extra={"description": ALGORITHM_EXPORT_DESCRIPTIONS["single_compartment"]}
    )

    filter_poles: FilterPoles | list[FilterPoles] = Field(
        default=1,
        title="Filter Poles",
        description=(
            "Number of exponential poles of the Rössert synaptic correction filter fit"
            f" (1-{MAX_FILTER_POLES}). More poles capture several dendritic time constants."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    filter_method: Literal["timedomain", "impedance"] = Field(
        default="timedomain",
        title="Filter Method",
        description=(
            "How dendritic filters are computed: 'timedomain' runs NEURON simulations of"
            " the detailed cell; 'impedance' uses a much faster passive frequency-domain"
            " approximation."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    strict_filters: bool = Field(
        default=True,
        title="Strict Filters",
        description=(
            "Fail the task when filter computation errors instead of silently using"
            " pass-through filters (no dendritic correction)."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    def pipeline_kwargs(self) -> dict[str, Any]:
        """Filter settings forwarded to ``SimplificationPipeline``."""
        return {
            "filter_poles": self.filter_poles,
            "filter_method": self.filter_method,
            "strict_filters": self.strict_filters,
        }


class LifNestAlgorithm(SimplificationAlgorithm):
    title: ClassVar[str] = ALGORITHM_EXPORT_TITLES["lif_nest"]
    algorithm_name: ClassVar[str] = "lif_nest"
    model_config = ConfigDict(
        json_schema_extra={"description": ALGORITHM_EXPORT_DESCRIPTIONS["lif_nest"]}
    )


class AdexNestAlgorithm(SimplificationAlgorithm):
    title: ClassVar[str] = ALGORITHM_EXPORT_TITLES["adex_nest"]
    algorithm_name: ClassVar[str] = "adex_nest"
    model_config = ConfigDict(
        json_schema_extra={"description": ALGORITHM_EXPORT_DESCRIPTIONS["adex_nest"]}
    )


class AdexBrian2Algorithm(SimplificationAlgorithm):
    title: ClassVar[str] = ALGORITHM_EXPORT_TITLES["adex_brian2"]
    algorithm_name: ClassVar[str] = "adex_brian2"
    model_config = ConfigDict(
        json_schema_extra={"description": ALGORITHM_EXPORT_DESCRIPTIONS["adex_brian2"]}
    )


class IzhikevichNestAlgorithm(SimplificationAlgorithm):
    title: ClassVar[str] = ALGORITHM_EXPORT_TITLES["izhikevich_nest"]
    algorithm_name: ClassVar[str] = "izhikevich_nest"
    model_config = ConfigDict(
        json_schema_extra={"description": ALGORITHM_EXPORT_DESCRIPTIONS["izhikevich_nest"]}
    )


class GlifNestAlgorithm(SimplificationAlgorithm):
    title: ClassVar[str] = ALGORITHM_EXPORT_TITLES["glif_nest"]
    algorithm_name: ClassVar[str] = "glif_nest"
    model_config = ConfigDict(
        json_schema_extra={"description": ALGORITHM_EXPORT_DESCRIPTIONS["glif_nest"]}
    )


class GifNestAlgorithm(SimplificationAlgorithm):
    title: ClassVar[str] = ALGORITHM_EXPORT_TITLES["gif_nest"]
    algorithm_name: ClassVar[str] = "gif_nest"
    model_config = ConfigDict(
        json_schema_extra={"description": ALGORITHM_EXPORT_DESCRIPTIONS["gif_nest"]}
    )


class NeuronReduceAlgorithm(SimplificationAlgorithm):
    title: ClassVar[str] = ALGORITHM_EXPORT_TITLES["neuron_reduce"]
    algorithm_name: ClassVar[str] = "neuron_reduce"
    model_config = ConfigDict(
        json_schema_extra={"description": ALGORITHM_EXPORT_DESCRIPTIONS["neuron_reduce"]}
    )


SIMPLIFICATION_ALGORITHM_BLOCKS = (
    SingleCompartmentAlgorithm
    | LifNestAlgorithm
    | AdexNestAlgorithm
    | AdexBrian2Algorithm
    | IzhikevichNestAlgorithm
    | GlifNestAlgorithm
    | GifNestAlgorithm
    | NeuronReduceAlgorithm
)

SimplificationAlgorithmUnion = Annotated[
    SIMPLIFICATION_ALGORITHM_BLOCKS,
    Discriminator("type"),
]

ALGORITHM_BLOCK_CLASSES: dict[str, type[SimplificationAlgorithm]] = {
    cls.algorithm_name: cls
    for cls in (
        SingleCompartmentAlgorithm,
        LifNestAlgorithm,
        AdexNestAlgorithm,
        AdexBrian2Algorithm,
        IzhikevichNestAlgorithm,
        GlifNestAlgorithm,
        GifNestAlgorithm,
        NeuronReduceAlgorithm,
    )
}


def default_simplification_algorithms() -> dict[str, SimplificationAlgorithmUnion]:
    """Return the default algorithm selection for a new simplification config."""
    return {"single_compartment": SingleCompartmentAlgorithm()}

from typing import Annotated, ClassVar

from pydantic import ConfigDict, Discriminator

from obi_one.scientific.blocks.simplification_algorithms.base import SimplificationAlgorithm
from obi_one.scientific.blocks.simplification_algorithms.metadata import (
    ALGORITHM_EXPORT_DESCRIPTIONS,
    ALGORITHM_EXPORT_TITLES,
)


class SingleCompartmentAlgorithm(SimplificationAlgorithm):
    title: ClassVar[str] = ALGORITHM_EXPORT_TITLES["single_compartment"]
    algorithm_name: ClassVar[str] = "single_compartment"
    model_config = ConfigDict(
        json_schema_extra={"description": ALGORITHM_EXPORT_DESCRIPTIONS["single_compartment"]}
    )


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


_SIMPLIFICATION_ALGORITHM_BLOCKS = (
    SingleCompartmentAlgorithm
    | LifNestAlgorithm
    | AdexNestAlgorithm
    | AdexBrian2Algorithm
    | IzhikevichNestAlgorithm
    | GlifNestAlgorithm
    | GifNestAlgorithm
)
SimplificationAlgorithmUnion = Annotated[
    _SIMPLIFICATION_ALGORITHM_BLOCKS,
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
    )
}


def default_simplification_algorithms() -> dict[str, SimplificationAlgorithmUnion]:
    """Return the default algorithm selection for a new simplification config."""
    return {"single_compartment": SingleCompartmentAlgorithm()}

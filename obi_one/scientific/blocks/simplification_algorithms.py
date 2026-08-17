from typing import Annotated, ClassVar

from pydantic import ConfigDict, Discriminator
from sonata_simplify.algorithms import ALGORITHM_DESCRIPTIONS, ALGORITHM_TITLES

from obi_one.core.block import Block

# Maps compound name -> (base_algorithm, exporter_name or None).
# Brian2 currently supports AdEx; other point-neuron algorithms use NEST.
ALGORITHM_EXPORT_MAP: dict[str, tuple[str, str | None]] = {
    "single_compartment": ("single_compartment", None),
    "lif_nest": ("lif", "nest:iaf_psc_alpha"),
    "adex_nest": ("adex", "nest:aeif_cond_alpha"),
    "adex_brian2": ("adex", "brian2:adex"),
    "izhikevich_nest": ("izhikevich", "nest:izhikevich"),
    "glif_nest": ("glif", "nest:glif_psc"),
    "gif_nest": ("gif", "nest:gif_cond_exp"),
}

# Display titles for compound names, extending the sonata_simplify metadata with
# the simulator suffix used by OBI-One.
ALGORITHM_EXPORT_TITLES: dict[str, str] = {
    "single_compartment": (
        f"{ALGORITHM_TITLES.get('single_compartment', 'Single Compartment')} (NEURON)"
    ),
    "lif_nest": f"{ALGORITHM_TITLES.get('lif', 'LIF')} (NEST)",
    "adex_nest": f"{ALGORITHM_TITLES.get('adex', 'AdEx')} (NEST)",
    "adex_brian2": f"{ALGORITHM_TITLES.get('adex', 'AdEx')} (Brian2)",
    "izhikevich_nest": f"{ALGORITHM_TITLES.get('izhikevich', 'Izhikevich')} (NEST)",
    "glif_nest": f"{ALGORITHM_TITLES.get('glif', 'GLIF')} (NEST)",
    "gif_nest": f"{ALGORITHM_TITLES.get('gif', 'GIF')} (NEST)",
}

# Descriptions remain sourced from sonata_simplify and are shared by all
# simulator variants of the same base algorithm.
ALGORITHM_EXPORT_DESCRIPTIONS: dict[str, str] = {
    name: ALGORITHM_DESCRIPTIONS.get(base, "") for name, (base, _) in ALGORITHM_EXPORT_MAP.items()
}


class SimplificationAlgorithm(Block):
    """Base class for a selectable circuit-simplification algorithm."""

    algorithm_name: ClassVar[str]


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


__all__ = [
    "ALGORITHM_BLOCK_CLASSES",
    "ALGORITHM_EXPORT_DESCRIPTIONS",
    "ALGORITHM_EXPORT_MAP",
    "ALGORITHM_EXPORT_TITLES",
    "AdexBrian2Algorithm",
    "AdexNestAlgorithm",
    "GifNestAlgorithm",
    "GlifNestAlgorithm",
    "IzhikevichNestAlgorithm",
    "LifNestAlgorithm",
    "SimplificationAlgorithm",
    "SimplificationAlgorithmUnion",
    "SingleCompartmentAlgorithm",
    "default_simplification_algorithms",
]

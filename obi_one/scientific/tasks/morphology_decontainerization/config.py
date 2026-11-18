"""Morphology decontainerization task configuration."""

from typing import ClassVar, Literal

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.library.circuit import Circuit


class MorphologyDecontainerizationScanConfig(ScanConfig):
    """Creates a circuit with individual morphology files instead of containerized morphologies,
    which involves the following steps:
    (1) Copy circuit to output location
    (2) Extract individual .h5 morphologies from an .h5 container
    (3) Convert .h5 morphologies to specified output format (.swc or .asc; skip if .h5)
    (4) Update the circuit config, pointing to the individual morphology folder
    (5) Delete .h5 container and .h5 files if that's not the specified output format
    (7) Check loading individual morphologies
    Important: The original circuit won't be modified! The circuit will be copied
               to the output location where all operations take place.
    """

    name: ClassVar[str] = "Morphology Decontainerization"
    description: ClassVar[str] = (
        "Creates a circuit with individual morphology files instead of containerized morphologies"
    )

    class Initialize(Block):
        circuit: Circuit | list[Circuit]
        output_format: Literal["h5", "asc", "swc"] | list[Literal["h5", "asc", "swc"]] = "h5"

    initialize: Initialize


class MorphologyDecontainerizationSingleConfig(
    MorphologyDecontainerizationScanConfig, SingleConfigMixin
):
    pass

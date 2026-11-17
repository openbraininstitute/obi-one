"""Morphology containerization task configuration."""

from typing import ClassVar

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.library.circuit import Circuit


class MorphologyContainerizationScanConfig(ScanConfig):
    """Creates a circuit with containerized morphologies instead of individual morphology files,
    which involves the following steps:
    (1) Copy circuit to output location
    (2) Convert morphologies to .h5, if not yet existing (from .swc or .asc)
    (3) Merge individual .h5 morphologies into an .h5 container
    (4) Update the circuit config, pointing to the .h5 container
    (5) Update .hoc files so that they will work with .h5 containers
    (6) Delete all individual morphologies
    (7) Check containerized morphologies
    Important: The original circuit won't be modified! The circuit will be copied
               to the output location where all operations take place.
    """

    name: ClassVar[str] = "Morphology Containerization"
    description: ClassVar[str] = (
        "Creates a circuit with containerized morphologies instead of individual morphology files"
    )

    class Initialize(Block):
        circuit: Circuit | list[Circuit]
        hoc_template_old: str
        hoc_template_new: str

    initialize: Initialize


class MorphologyContainerizationSingleConfig(
    MorphologyContainerizationScanConfig, SingleConfigMixin
):
    pass

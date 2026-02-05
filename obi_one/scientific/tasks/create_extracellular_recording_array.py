import json
import logging
import os
import shutil
import tempfile
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal

import bluepysnap as snap
import bluepysnap.circuit_validation
import h5py
import numpy as np
import tqdm
from bluepysnap import BluepySnapError
from brainbuilder.utils.sonata import split_population
from entitysdk import Client, models, types
from pydantic import ConfigDict, Field, PrivateAttr

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.constants import (
    _COORDINATE_CONFIG_FILENAME,
    _MAX_SMALL_MICROCIRCUIT_SIZE,
    _NEURON_PAIR_SIZE,
    _SCAN_CONFIG_FILENAME,
)
from obi_one.scientific.tasks.generate_simulation_configs import CircuitDiscriminator
from obi_one.scientific.unions.unions_extracellular_locations import ExtracellularLocationsUnion

L = logging.getLogger(__name__)
_RUN_VALIDATION = False


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"


class CreateExtracellularRecordingArrayScanConfig(ScanConfig):
    """Description."""

    single_coord_class_name: ClassVar[str] = "CreateExtracellularRecordingArraySingleConfig"
    name: ClassVar[str] = "Create Extracellular Recording Array"
    description: ClassVar[str] = (
        "Description."
    )

    _campaign: models.CircuitExtractionCampaign = None

    model_config = ConfigDict(
        json_schema_extra={
            "ui_enabled": True,
            "group_order": [BlockGroup.SETUP],
        }
    )

    class Initialize(Block):
        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
            title="Circuit",
            description="Parent circuit to extract a sub-circuit from.",
            json_schema_extra={
                "ui_element": "model_identifier",
            },
        )
        calculation_method: Literal["PointSource", "LineSource", "Reciprocity", "DipoleReciprocity", ] = Field(
            title="Calculation Method",
            description="Method to calculate extracellular signals from the specified neuron set and"
            " electrode locations.",
            json_schema_extra={
                "ui_element": "string_selection_enhanced",
            },
        )
        # do_virtual: bool = Field(
        #     default=True,
        #     title="Include Virtual Populations",
        #     description="Include virtual neurons which target the cells contained in the specified"
        #     " neuron set (together with their connectivity onto the specified neuron set) in the"
        #     " extracted sub-circuit.",
        #     json_schema_extra={
        #         "ui_element": "boolean_input",
        #     },
        # )
        # create_external: bool = Field(
        #     default=True,
        #     title="Create External Population",
        #     description="Convert (non-virtual) neurons which are outside of the specified neuron"
        #     " set, but which target the cells contained therein, into a new external population"
        #     " of virtual neurons (together with their connectivity onto the specified neuron set).",
        #     json_schema_extra={
        #         "ui_element": "boolean_input",
        #     },
        # )

    info: Info = Field(
        title="Info",
        description="Information...",
        json_schema_extra={
            "ui_element": "block_single",
            "group": BlockGroup.SETUP,
            "group_order": 0,
        },
    )
    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the extracellular recording array creation.",
        json_schema_extra={
            "ui_element": "block_single",
            "group": BlockGroup.SETUP,
            "group_order": 1,
        },
    )
    extracellular_locations: ExtracellularLocationsUnion = Field(
        title="Extracellular Locations",
        description="Electrode locations for recording extracellular signals.",
        json_schema_extra={
            "ui_element": "block_union",
            "group": BlockGroup.SETUP,
            "group_order": 2,
        },
    )
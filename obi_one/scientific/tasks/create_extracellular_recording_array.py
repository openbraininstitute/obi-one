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
    ELECTRODE_POSITIONS = "Electrode Location"


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
        calculation_method: Literal["PointSource", "LineSource", "ObjectiveCSD"] = Field(
            title="Calculation Method",
            description="Method to calculate extracellular signals from the specified neuron set and"
            " electrode locations.",
            json_schema_extra={
                "ui_element": "string_selection_enhanced",
                "title_by_key": {
                    "PointSource": "Point Source",
                    "LineSource": "Line Source",
                    "ObjectiveCSD": "Objective CSD",
                },
                "description_by_key": {
                    "PointSource": "Calculate extracellular signals using the Point Source method.",
                    "LineSource": "Calculate extracellular signals using the Line Source method.",
                    "ObjectiveCSD": "Calculate extracellular signals using the Objective CSD method.",
                }
            },
        )

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
            "group": BlockGroup.ELECTRODE_POSITIONS,
            "group_order": 0,
        },
    )
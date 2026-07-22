from pathlib import Path
from typing import ClassVar

import entitysdk
from pydantic import Field

from obi_one.core.exception import OBIONEError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.recordings.base import Recording
from obi_one.scientific.from_id.extracellular_recording_array_from_id import (
    SimulatableExtracellularRecordingArrayFromID,
)
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    resolve_neuron_set_ref_to_node_set,
)

ELECTRODES_FILE_SUFFIX = "_electrodes.h5"


class ExtracellularElectrodeArrayRecordingBlock(Recording):
    """Records the extracellular signal (LFP) seen by each electrode of a recording array.

    The array's weight matrix maps the membrane current of every segment of the recorded neurons
    onto every electrode, so the recorded neuron set must be part of the circuit the array was
    built for.
    """

    title: ClassVar[str] = "Extracellular Electrode Array Recording"

    electrode_array: SimulatableExtracellularRecordingArrayFromID = Field(
        title="Extracellular Recording Array",
        description=(
            "Extracellular recording array to record with. Must have been built for the circuit "
            "being simulated."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER,
            SchemaKey.PARAMETER_ORDER_PRIORITY: 100,
        },
    )

    def _stage_electrodes_file(self, db_client: entitysdk.client.Client | None) -> Path:
        """Download the array's weight matrix next to the simulation config.

        Returns:
            Path of the downloaded file relative to the simulation config directory, which is how
            SONATA resolves it.
        """
        if db_client is None:
            msg = (
                f"Recording '{self.block_name}' needs a database client to download the "
                "weight matrix of its extracellular recording array."
            )
            raise OBIONEError(msg)

        config_directory = self._sonata_simulation_config_directory
        if config_directory is None:
            msg = (
                f"Recording '{self.block_name}' needs the simulation config directory to "
                "download the weight matrix of its extracellular recording array into."
            )
            raise OBIONEError(msg)

        electrodes_file = self.electrode_array.download_electrode_file(
            dest_dir=config_directory,
            db_client=db_client,
            file_name=f"{self.block_name}{ELECTRODES_FILE_SUFFIX}",
        )
        return electrodes_file.relative_to(config_directory)

    def _generate_config(self, db_client: entitysdk.client.Client | None = None) -> dict:
        return {
            self.block_name: {
                "cells": resolve_neuron_set_ref_to_node_set(
                    self.neuron_set, self._default_node_set
                ),
                "type": "lfp",
                # LFP sums the membrane current over the whole neuron, not just the soma, and the
                # weight matrix holds a weight per segment.
                "sections": "all",
                "dt": self.dt,
                "start_time": self._start_time,
                "end_time": self._end_time,
                "electrodes_file": str(self._stage_electrodes_file(db_client)),
            }
        }

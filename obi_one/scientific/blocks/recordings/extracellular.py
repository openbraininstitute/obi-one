from typing import ClassVar

import entitysdk
from entitysdk.types import EntityType
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.recordings.base import Recording
from obi_one.scientific.from_id.extracellular_recording_array_from_id import (
    SimulatableExtracellularRecordingArrayFromID,
)
from obi_one.scientific.library.entity_property_types import (
    CircuitUsability,
    MappedPropertiesGroup,
)
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    resolve_neuron_set_ref_to_node_set,
)


class ExtracellularElectrodeArrayRecordingBlock(Recording):
    """Records the extracellular signal (LFP) seen by each electrode of a recording array.

    The array's weight matrix maps the membrane current of every segment of the recorded neurons
    onto every electrode, so the recorded neuron set must be part of the circuit the array was
    built for.
    """

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_EXTRACELLULAR_RECORDINGS,
            SchemaKey.FALSE_MESSAGE: (
                "Extracellular recordings are only available for circuits larger than a small "
                "microcircuit."
            ),
        },
    }

    title: ClassVar[str] = "Extracellular Electrode Array Recording"

    electrode_array: SimulatableExtracellularRecordingArrayFromID = Field(
        title="Extracellular Recording Array",
        description=(
            "Extracellular recording array to record with. Must have been built for the circuit "
            "being simulated."
        ),
        json_schema_extra={
            SchemaKey.PARAMETER_ORDER_PRIORITY: 100,
            SchemaKey.UI_ELEMENT: UIElement.MODEL_SELECTOR_SINGLE,
            SchemaKey.ENTITY_QUERY: {
                "type": EntityType.simulatable_extracellular_recording_array,
                SchemaKey.FILTERS: {
                    # A list, not a value: the frontend fills it with the id from VALUE_FROM.
                    "circuit_id": ["circuit_id"],
                },
                SchemaKey.VALUE_FROM: "initialize.circuit",
            },
        },
    )

    def _generate_config(
        self,
        db_client: entitysdk.client.Client | None = None,  # ruff: ignore[unused-method-argument]
    ) -> dict:
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
                # The weight matrix covers every segment of the circuit, so it is not downloaded
                # here. entitysdk's stage_simulation fetches it when the simulation is run, for
                # every array linked to the Simulation entity, recognising which report it belongs
                # to by this file name and rewriting the path to the staged copy.
                "electrodes_file": f"{self.electrode_array.id_str}.h5",
            }
        }

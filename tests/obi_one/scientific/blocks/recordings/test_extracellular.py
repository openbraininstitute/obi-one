import json
from pathlib import Path
from uuid import UUID

import libsonata
import pytest

from obi_one.core.exception import OBIONEError
from obi_one.core.schema import SchemaKey
from obi_one.scientific.blocks.recordings.extracellular import (
    ExtracellularElectrodeArrayRecordingBlock,
    SummedExtracellularElectrodeArrayRecordingBlock,
    TimeWindowExtracellularElectrodeArrayRecordingBlock,
    TimeWindowSummedExtracellularElectrodeArrayRecordingBlock,
)
from obi_one.scientific.from_id.extracellular_recording_array_from_id import (
    SimulatableExtracellularRecordingArrayFromID,
)
from obi_one.scientific.library.constants import SIMULATION_TIMESTEP_MILLISECONDS
from obi_one.scientific.library.entity_property_types import (
    CircuitUsability,
    MappedPropertiesGroup,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationScanConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model import (
    MEModelSimulationScanConfig,
)

ARRAY_ID = "9f8ac5a5-4b6c-4e57-9a2f-2e3f7d0b1c44"


class _ClientThatMustNotBeUsed:
    """Fails the test on any use: emitting the report must not touch the database."""

    def __getattr__(self, name):
        msg = f"the recording used the database client ({name})"
        raise AssertionError(msg)


def _recording(
    name="LFPRecording", dt=0.1, block=ExtracellularElectrodeArrayRecordingBlock, **window
):
    recording = block(
        electrode_array=SimulatableExtracellularRecordingArrayFromID(id_str=ARRAY_ID),
        dt=dt,
        **window,
    )
    recording.set_block_name(name)
    return recording


class TestExtracellularElectrodeArrayRecordingBlock:
    def test_generates_sonata_lfp_report(self):
        reports = _recording().config(
            SIMULATION_TIMESTEP_MILLISECONDS, end_time=100.0, default_node_set="AllBiophysical"
        )

        assert reports == {
            "LFPRecording": {
                "cells": "AllBiophysical",
                "type": "lfp",
                "sections": "all",
                "unit": "V",
                "dt": 0.1,
                "start_time": 0.0,
                "end_time": 100.0,
                "electrodes_file": f"{ARRAY_ID}.h5",
            }
        }

    def test_electrodes_file_is_named_after_the_array(self):
        """entitysdk's stage_simulation reads the array id back out of the file name's stem."""
        reports = _recording().config(SIMULATION_TIMESTEP_MILLISECONDS, end_time=100.0)

        electrodes_file = Path(reports["LFPRecording"]["electrodes_file"])
        assert UUID(electrodes_file.stem) == UUID(ARRAY_ID)

    def test_does_not_download_the_weight_matrix(self):
        """The matrix covers the whole circuit; it is staged when the simulation is run."""
        reports = _recording().config(
            SIMULATION_TIMESTEP_MILLISECONDS,
            end_time=100.0,
            db_client=_ClientThatMustNotBeUsed(),
        )

        assert reports["LFPRecording"]["electrodes_file"] == f"{ARRAY_ID}.h5"

    def test_report_is_accepted_by_libsonata(self, tmp_path):
        """`write_simulation_config` validates with libsonata, which is strict about lfp reports.

        Nothing exists at the path: libsonata does not need the file, only the simulation does.
        """
        reports = _recording().config(SIMULATION_TIMESTEP_MILLISECONDS, end_time=100.0)

        sonata_config = {
            "version": 1,
            "network": "circuit_config.json",
            "run": {"tstop": 100.0, "dt": 0.025, "random_seed": 1},
            "reports": reports,
        }
        parsed = libsonata.SimulationConfig(json.dumps(sonata_config), str(tmp_path))

        report = parsed.report("LFPRecording")
        assert report.type == libsonata.SimulationConfig.Report.Type.lfp
        assert report.electrodes_file == str(tmp_path / f"{ARRAY_ID}.h5")

    def test_the_signal_is_labelled_in_volts(self, tmp_path):
        """The weights are in V/nA (SONATA spec); libsonata would otherwise default the unit to mV.

        neurodamus passes the report's unit to the writer, which labels the output file with it.
        """
        reports = _recording().config(SIMULATION_TIMESTEP_MILLISECONDS, end_time=100.0)
        sonata_config = {
            "version": 1,
            "network": "circuit_config.json",
            "run": {"tstop": 100.0, "dt": 0.025, "random_seed": 1},
            "reports": reports,
        }

        parsed = libsonata.SimulationConfig(json.dumps(sonata_config), str(tmp_path))

        assert parsed.report("LFPRecording").unit == "V"


class TestSummedExtracellularElectrodeArrayRecordingBlock:
    def test_generates_a_summed_sonata_lfp_report(self):
        reports = _recording(block=SummedExtracellularElectrodeArrayRecordingBlock).config(
            SIMULATION_TIMESTEP_MILLISECONDS, end_time=100.0, default_node_set="AllBiophysical"
        )

        assert reports == {
            "LFPRecording": {
                "cells": "AllBiophysical",
                "type": "lfp",
                "sections": "all",
                "unit": "V",
                "dt": 0.1,
                "start_time": 0.0,
                "end_time": 100.0,
                "electrodes_file": f"{ARRAY_ID}.h5",
                "method": "sum",
            }
        }

    @pytest.mark.parametrize(
        ("block", "method"),
        [
            (SummedExtracellularElectrodeArrayRecordingBlock, "sum"),
            (ExtracellularElectrodeArrayRecordingBlock, "by_cell"),
        ],
    )
    def test_libsonata_reads_the_method(self, tmp_path, block, method):
        reports = _recording(block=block).config(SIMULATION_TIMESTEP_MILLISECONDS, end_time=100.0)
        sonata_config = {
            "version": 1,
            "network": "circuit_config.json",
            "run": {"tstop": 100.0, "dt": 0.025, "random_seed": 1},
            "reports": reports,
        }

        parsed = libsonata.SimulationConfig(json.dumps(sonata_config), str(tmp_path))

        assert parsed.report("LFPRecording").method.name == method


class TestTimeWindow:
    @pytest.mark.parametrize(
        ("block", "method"),
        [
            (TimeWindowSummedExtracellularElectrodeArrayRecordingBlock, {"method": "sum"}),
            (TimeWindowExtracellularElectrodeArrayRecordingBlock, {}),
        ],
    )
    def test_records_only_the_window(self, block, method):
        reports = _recording(block=block, start_time=20.0, end_time=60.0).config(
            SIMULATION_TIMESTEP_MILLISECONDS, end_time=100.0, default_node_set="AllBiophysical"
        )

        assert reports == {
            "LFPRecording": {
                "cells": "AllBiophysical",
                "type": "lfp",
                "sections": "all",
                "unit": "V",
                "dt": 0.1,
                "start_time": 20.0,
                "end_time": 60.0,
                "electrodes_file": f"{ARRAY_ID}.h5",
                **method,
            }
        }

    @pytest.mark.parametrize(
        "block",
        [
            TimeWindowSummedExtracellularElectrodeArrayRecordingBlock,
            TimeWindowExtracellularElectrodeArrayRecordingBlock,
        ],
    )
    def test_the_window_must_end_after_it_starts(self, block):
        with pytest.raises(OBIONEError, match="End time must be later than start time"):
            _recording(block=block, start_time=60.0, end_time=20.0)

    def test_is_greyed_out_like_its_full_experiment_block(self):
        for window, full in [
            (
                TimeWindowSummedExtracellularElectrodeArrayRecordingBlock,
                SummedExtracellularElectrodeArrayRecordingBlock,
            ),
            (
                TimeWindowExtracellularElectrodeArrayRecordingBlock,
                ExtracellularElectrodeArrayRecordingBlock,
            ),
        ]:
            assert (
                window.model_json_schema()[SchemaKey.BLOCK_USABILITY_DICTIONARY]
                == full.model_json_schema()[SchemaKey.BLOCK_USABILITY_DICTIONARY]
            )


class TestCircuitUsability:
    def test_summed_is_offered_only_where_the_circuit_allows_extracellular_recordings(self):
        """The frontend greys the block out when the circuit's usability flag is false."""
        schema = SummedExtracellularElectrodeArrayRecordingBlock.model_json_schema()
        usability = schema[SchemaKey.BLOCK_USABILITY_DICTIONARY]

        assert usability[SchemaKey.PROPERTY_GROUP] == MappedPropertiesGroup.CIRCUIT
        assert usability[SchemaKey.PROPERTY] == CircuitUsability.SHOW_EXTRACELLULAR_RECORDINGS
        assert usability[SchemaKey.FALSE_MESSAGE]

    def test_per_neuron_has_its_own_flag(self):
        """Off for every circuit for now (see the circuit properties endpoint), so greyed out."""
        schema = ExtracellularElectrodeArrayRecordingBlock.model_json_schema()
        usability = schema[SchemaKey.BLOCK_USABILITY_DICTIONARY]

        assert usability[SchemaKey.PROPERTY_GROUP] == MappedPropertiesGroup.CIRCUIT
        assert (
            usability[SchemaKey.PROPERTY] == CircuitUsability.SHOW_PER_CELL_EXTRACELLULAR_RECORDINGS
        )
        assert usability[SchemaKey.FALSE_MESSAGE]


SUMMED_BLOCKS = [
    SummedExtracellularElectrodeArrayRecordingBlock,
    TimeWindowSummedExtracellularElectrodeArrayRecordingBlock,
]
PER_NEURON_BLOCKS = [
    ExtracellularElectrodeArrayRecordingBlock,
    TimeWindowExtracellularElectrodeArrayRecordingBlock,
]


class TestCircuitRecordingUnion:
    @pytest.mark.parametrize("block", SUMMED_BLOCKS)
    def test_summed_recording_offered_by_circuit_simulations(self, block):
        scan_config = CircuitSimulationScanConfig.empty_config()
        scan_config.add(_recording(block=block), name="LFPRecording")

        assert isinstance(scan_config.recordings["LFPRecording"], block)

    @pytest.mark.parametrize("block", PER_NEURON_BLOCKS)
    def test_per_neuron_recording_not_offered_by_circuit_simulations(self, block):
        """Left out of the recordings union, so neither the UI nor a config can use it."""
        scan_config = CircuitSimulationScanConfig.empty_config()

        with pytest.raises(KeyError, match=block.__name__):
            scan_config.add(_recording(block=block), name="LFPRecording")

    @pytest.mark.parametrize("block", SUMMED_BLOCKS + PER_NEURON_BLOCKS)
    def test_extracellular_recording_rejected_by_single_cell_simulations(self, block):
        """MEModel simulations have no circuit-wide weight matrix, so cannot record LFP."""
        scan_config = MEModelSimulationScanConfig.empty_config()

        # Not in the block mapping, because it is not part of that config's recordings union.
        with pytest.raises(KeyError, match=block.__name__):
            scan_config.add(_recording(block=block), name="LFPRecording")

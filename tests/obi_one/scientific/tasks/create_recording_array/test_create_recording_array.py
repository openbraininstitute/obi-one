import json

import pytest

import obi_one.scientific.tasks.create_recording_array.create_recording_array as test_module

pytest.importorskip("bluerecording")


class TestWriteElectrodeJson:
    """Tests for write_electrode_json."""

    def test_writes_correct_format(self, tmp_path):
        """Writes electrode positions in bluerecording JSON format."""

        class FakeBlock:
            def get_global_electrode_xyz_locations(self):
                return [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)]

        electrode_locations = {"probe_a": FakeBlock()}
        output_path = tmp_path / "electrodes.json"

        result = test_module._write_electrode_json(electrode_locations, "PointSource", output_path)

        assert result == output_path
        data = json.loads(output_path.read_text())
        assert len(data) == 2
        assert data[0]["name"] == "probe_a_electrode_0"
        assert data[0]["x"] == pytest.appox(1.0)
        assert data[0]["y"] == pytest.appox(2.0)
        assert data[0]["z"] == pytest.appox(3.0)
        assert data[0]["type"] == "PointSource"
        assert data[1]["name"] == "probe_a_electrode_1"

    def test_multiple_blocks(self, tmp_path):
        """Handles multiple electrode location blocks."""

        class FakeBlockA:
            def get_global_electrode_xyz_locations(self):
                return [(0.0, 0.0, 0.0)]

        class FakeBlockB:
            def get_global_electrode_xyz_locations(self):
                return [(10.0, 10.0, 10.0)]

        electrode_locations = {"A": FakeBlockA(), "B": FakeBlockB()}
        output_path = tmp_path / "electrodes.json"

        test_module._write_electrode_json(electrode_locations, "LineSource", output_path)

        data = json.loads(output_path.read_text())
        assert len(data) == 2
        assert data[0]["name"] == "A_electrode_0"
        assert data[1]["name"] == "B_electrode_0"
        assert data[1]["type"] == "LineSource"

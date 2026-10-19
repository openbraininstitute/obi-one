import json
from types import SimpleNamespace

import pytest

from obi_one.scientific.library.emodel_parameters import _parse_optimization_parameters
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.registration import (
    write_emodel_optimization_output,
)

FINAL = {
    "DM__1": {
        "emodel": "DM",
        "etype": "cADpyr",
        "ttype": None,
        "mtype": "L5_TPC:C",
        "species": "Rattus norvegicus",
        "brain_region": "SSp-ll5",
        "iteration": None,
        "synapse_class": None,
        "score": 3.0,
        "parameters": {"g_pas.all": 5e-05, "gNaTgbar_NaTg.axonal": 0.56},
        "fitness": {"IDrest_130.soma.v.Spikecount": 1.0, "APWaveform.soma.v.AP_amplitude": 2.0},
        "features": {"IDrest_130.soma.v.Spikecount": 17.0},
        "validation_fitness": {},
        "validated": None,
        "seed": 1,
    }
}


class TestWriteEModelOptimizationOutput:
    def test_resource_format(self, tmp_path):
        final_path = tmp_path / "final.json"
        final_path.write_text(json.dumps(FINAL))

        out = write_emodel_optimization_output(final_path, "DM", 1, tmp_path / "out")

        assert out.name == "emodel_optimization_output.json"
        data = json.loads(out.read_text())
        assert set(data) == {
            "fitness",
            "parameter",
            "score",
            "features",
            "scoreValidation",
            "passedValidation",
            "seed",
        }
        assert data["fitness"] == pytest.approx(3.0)
        assert {"name": "g_pas.all", "value": 5e-05, "unitCode": ""} in data["parameter"]
        assert data["seed"] == 1

        params = _parse_optimization_parameters(
            data["parameter"], SimpleNamespace(ion_channel_models=[])
        )
        assert params

    def test_missing_entry_raises(self, tmp_path):
        final_path = tmp_path / "final.json"
        final_path.write_text(json.dumps(FINAL))
        with pytest.raises(ValueError, match="No entry"):
            write_emodel_optimization_output(final_path, "DM", 2, tmp_path)

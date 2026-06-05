import json

import libsonata
import pytest

from obi_one.utils import sonata as test_module


def test_write_simulation_config(tmp_path):
    filepath = tmp_path / "simulation_config.json"

    config = {"run": {"dt": 0.1, "tstop": 1.0, "random_seed": 0}}

    test_module.write_simulation_config(config=config, output_path=filepath)
    res_config = json.loads(filepath.read_bytes())

    assert res_config == config

    with pytest.raises(libsonata.SonataError):
        test_module.write_simulation_config(config={}, output_path=filepath)

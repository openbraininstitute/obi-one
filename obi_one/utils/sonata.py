import json
from pathlib import Path

import libsonata


def write_simulation_config(config: dict, output_path: Path) -> None:
    """Write simulation config to file."""
    serialized_data = json.dumps(config, indent=2)

    # ensure config is compatible with libsonata
    libsonata.SimulationConfig(serialized_data, ".")

    output_path.write_text(serialized_data, encoding="utf-8")

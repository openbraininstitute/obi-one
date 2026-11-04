"""Cover SimulationSingleConfigMixin.create_single_entity_with_config return path."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from entitysdk.models import Simulation

from obi_one.core.single import SingleCoordinateScanParams
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)


def test_create_single_entity_with_config_returns_registered_simulation(tmp_path):
    coordinate_root = tmp_path / "0"
    coordinate_root.mkdir()
    (coordinate_root / "obi_one_coordinate.json").write_text("{}")

    config = CircuitSimulationSingleConfig.model_construct(
        idx=0,
        initialize=SimpleNamespace(circuit=CircuitFromID(id_str=str(uuid4()))),
        coordinate_output_root=coordinate_root,
        single_coordinate_scan_params=SingleCoordinateScanParams(),
    )

    registered = MagicMock(spec=Simulation)
    registered.id = uuid4()
    db_client = MagicMock()
    db_client.register_entity.return_value = registered
    campaign = MagicMock()
    campaign.id = uuid4()

    with patch.object(
        CircuitSimulationSingleConfig,
        "entity_id_for_campaign_entity_generation",
        return_value=uuid4(),
    ):
        result = config.create_single_entity_with_config(campaign=campaign, db_client=db_client)

    assert result is registered
    db_client.register_entity.assert_called_once()
    db_client.upload_file.assert_called_once()
    assert config._single_entity is registered

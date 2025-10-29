import abc
import logging
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar, Literal

import entitysdk
from pydantic import Field, PrivateAttr

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig

import logging
from pathlib import Path
from typing import ClassVar

import entitysdk
from pydantic import PrivateAttr

from obi_one.core.block import Block
from obi_one.core.task import Task
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.memodel_circuit import MEModelCircuit

from obi_one.scientific.tasks.generate_simulation_configs import (
    CircuitSimulationSingleConfig,
    MEModelSimulationSingleConfig,
    MEModelWithSynapsesCircuitSimulationSingleConfig,
)

L = logging.getLogger(__name__)


class SkeletonizationScanConfig(ScanConfig, abc.ABC):
    """Abstract base class for skeletonization scan configurations."""

    single_coord_class_name: ClassVar[str]
    name: ClassVar[str] = "Skeletonization Campaign"
    description: ClassVar[str] = "Skeletonization campaign"

    # _campaign: entitysdk.models.SimulationCampaign = None

    class Initialize(Block):
        circuit: None
      
        v_init: list[float] | float = Field(
            default=-80.0,
            title="Initial Voltage",
            description="Initial membrane potential in millivolts (mV).",
            units="mV",
        )
        

    info: Info = Field(
        title="Info",
        description="Information about the skeletonization campaign.",
        # group=BlockGroup.SETUP_BLOCK_GROUP,
        # group_order=0,
    )

    def create_campaign_entity_with_config(
        self,
        output_root: Path,
        multiple_value_parameters_dictionary: dict | None = None,
        db_client: entitysdk.client.Client = None,
    ) -> entitysdk.models.SimulationCampaign:
        # """Initializes the simulation campaign in the database."""
        # L.info("1. Initializing simulation campaign in the database...")
        # if multiple_value_parameters_dictionary is None:
        #     multiple_value_parameters_dictionary = {}

        # L.info("-- Register SimulationCampaign Entity")
        # if isinstance(
        #     self.initialize.circuit,
        #     (CircuitFromID, MEModelFromID, MEModelWithSynapsesCircuitFromID),
        # ):
        #     entity_id = self.initialize.circuit.id_str
        # elif isinstance(self.initialize.circuit, list):
        #     if len(self.initialize.circuit) != 1:
        #         msg = "Only single circuit/MEModel currently supported for \
        #             simulation campaign database persistence."
        #         raise OBIONEError(msg)
        #     entity_id = self.initialize.circuit[0].id_str

        # self._campaign = db_client.register_entity(
        #     entitysdk.models.SimulationCampaign(
        #         name=self.info.campaign_name,
        #         description=self.info.campaign_description,
        #         entity_id=entity_id,
        #         scan_parameters=multiple_value_parameters_dictionary,
        #     )
        # )

        # L.info("-- Upload campaign_generation_config")
        # _ = db_client.upload_file(
        #     entity_id=self._campaign.id,
        #     entity_type=entitysdk.models.SimulationCampaign,
        #     file_path=output_root / "run_scan_config.json",
        #     file_content_type="application/json",
        #     asset_label="campaign_generation_config",
        # )

        return self._campaign

    def create_campaign_generation_entity(
        self, simulations: list[entitysdk.models.Simulation], db_client: entitysdk.client.Client
    ) -> None:
        L.info("3. Saving completed simulation campaign generation")

        # L.info("-- Register SimulationGeneration Entity")
        # db_client.register_entity(
        #     entitysdk.models.SimulationGeneration(
        #         start_time=datetime.now(UTC),
        #         used=[self._campaign],
        #         generated=simulations,
        #     )
        # )



class SkeletonizationSingleConfig(
    SkeletonizationScanConfig, SingleConfigMixin
):
    _single_entity: entitysdk.models.Simulation

    @property
    def single_entity(self) -> entitysdk.models.Simulation:
        return self._single_entity

    def create_single_entity_with_config(
        self, campaign: entitysdk.models.SimulationCampaign, db_client: entitysdk.client.Client
    ) -> entitysdk.models.Simulation:
        """Saves the simulation to the database."""
        L.info(f"2.{self.idx} Saving simulation {self.idx} to database...")


        # L.info("-- Register Simulation Entity")
        # self._single_entity = db_client.register_entity(
        #     entitysdk.models.Simulation(
        #         name=f"Simulation {self.idx}",
        #         description=f"Simulation {self.idx}",
        #         scan_parameters=self.single_coordinate_scan_params.dictionary_representaiton(),
        #         entity_id=self.initialize.circuit.id_str,
        #         simulation_campaign_id=campaign.id,
        #     )
        # )

        # L.info("-- Upload simulation_generation_config")
        # _ = db_client.upload_file(
        #     entity_id=self.single_entity.id,
        #     entity_type=entitysdk.models.Simulation,
        #     file_path=Path(self.coordinate_output_root, "run_coordinate_instance.json"),
        #     file_content_type="application/json",
        #     asset_label="simulation_generation_config",
        # )





class GenerateSimulationTask(Task):
    config: (
        CircuitSimulationSingleConfig
        | MEModelSimulationSingleConfig
        | MEModelWithSynapsesCircuitSimulationSingleConfig
    )

    CONFIG_FILE_NAME: ClassVar[str] = "simulation_config.json"
    NODE_SETS_FILE_NAME: ClassVar[str] = "node_sets.json"

    _sonata_config: dict = PrivateAttr(default={})
    _circuit: Circuit | MEModelCircuit | None = PrivateAttr(default=None)
    _entity_cache: bool = PrivateAttr(default=False)

    def execute(
        self, *, db_client: entitysdk.client.Client = None, entity_cache: bool = False
    ) -> None:
        pass
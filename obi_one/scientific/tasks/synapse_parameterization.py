import logging

from entitysdk import Client
from pydantic import Field
from typing import ClassVar

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID

L = logging.getLogger(__name__)


class SynapseParameterizationSingleConfig(OBIBaseModel, SingleConfigMixin):
    name: ClassVar[str] = "Synapse parameterization"
    description: ClassVar[str] = "Generates a physiological parameterization of an anatomical synaptome or replaces an existing paramterization."

    class Initialize(Block):
        synaptome: CircuitFromID = Field(
            title="Synaptome", description="Synaptome (i.e., circuit of scale single) to (re-)parameterize."
        )
        pathway_param_dict: dict = Field(
            title="Pathway parameters", description="Synapse physiology distribution parameters for all pathways in the ConnPropsModel format of Connectome-Manipulator."
        )  # TODO: This may be replaced by dedicated entities
        overwrite_if_exists: bool = Field(
            title="Overwrite", description="Overwrite if a parameterization exists already.", default=False
        )

    initialize: Initialize


class SynapseParameterizationTask(Task):
    config: SynapseParameterizationSingleConfig

    def execute(self, *, db_client: Client = None, entity_cache: bool = False) -> None:
        if db_client is None:
            msg = "The synapse parameterization task requires a working db_client!"
            raise ValueError(msg)

        L.info("Running synapse parameterization...")
        L.error("Not yet implemented!")

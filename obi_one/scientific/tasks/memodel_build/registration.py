"""Entity registration for the ME-model build task.

The ME-model is registered after calibration, once holding and threshold currents are known.
"""

import logging

import entitysdk
from entitysdk.models import (
    BrainRegion,
    CellMorphology,
    Contribution,
    EModel,
    MEModel,
    Person,
    Role,
    Species,
)
from entitysdk.registration.classification import (
    register_etype_classification,
    register_mtype_classification,
)
from entitysdk.registration.memodel import register_memodel_calibration_result
from entitysdk.types import ID, ValidationStatus

from obi_one.scientific.tasks.memodel_build.config import MEModelBuildSingleConfig

L = logging.getLogger(__name__)

CREATOR_ROLE_NAME = "creator role"


def register_memodel(
    config: MEModelBuildSingleConfig,
    db_client: entitysdk.Client,
    *,
    morphology: CellMorphology,
    emodel: EModel,
    species: Species,
    brain_region: BrainRegion,
    holding_current: float,
    threshold_current: float,
    rin: float | None,
    authorized_public: bool,
) -> MEModel:
    """Register the ME-model, classifications, calibration result, and creator contribution.

    ``entitysdk.registration.memodel.register_memodel`` is not used: it requires a
    ``license`` and has no ``strain``.
    """
    memodel = db_client.register_entity(
        MEModel(
            name=config.info.campaign_name,
            description=config.info.campaign_description,
            morphology=morphology,
            emodel=emodel,
            species=species,
            # morphology.subject is required by the caller (metadata_entities raises otherwise)
            strain=morphology.subject.strain,  # ty:ignore[unresolved-attribute]
            brain_region=brain_region,
            holding_current=holding_current,
            threshold_current=threshold_current,
            validation_status=ValidationStatus.created,
            authorized_public=authorized_public,
        )
    )
    L.info("MEModel registered: %s", memodel.id)

    for mtype in morphology.mtypes or []:
        register_mtype_classification(client=db_client, entity=memodel, mtype_class=mtype)
    for etype in emodel.etypes or []:
        register_etype_classification(client=db_client, entity=memodel, etype_class=etype)

    register_memodel_calibration_result(
        client=db_client,
        calibrated_entity_id=memodel.id,
        holding_current=holding_current,
        threshold_current=threshold_current,
        rin=rin,
        authorized_public=authorized_public,
    )
    _register_creator(db_client=db_client, memodel=memodel)
    return memodel


def _register_creator(db_client: entitysdk.Client, memodel: MEModel) -> None:
    creator = db_client.search_entity(
        entity_type=Person, query={"sub_id": memodel.created_by.id}, limit=1
    ).one()
    creator_role = db_client.search_entity(
        entity_type=Role, query={"name": CREATOR_ROLE_NAME}, limit=1
    ).one()
    db_client.register_entity(Contribution(agent=creator, role=creator_role, entity=memodel))


def set_validation_status(
    db_client: entitysdk.Client, *, memodel_id: ID, validation_status: ValidationStatus
) -> None:
    db_client.update_entity(
        entity_id=memodel_id,
        entity_type=MEModel,
        attrs_or_entity={"validation_status": validation_status},
    )
    L.info("MEModel %s validation_status: %s", memodel_id, validation_status)

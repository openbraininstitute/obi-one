"""Entity registration for the ME-model build task.

The ME-model is registered before it is calibrated and validated, so it exists (and can be
linked from the execution activity) while the slow part runs.
"""

import logging

import entitysdk
from entitysdk.models import Contribution, MEModel, Person, Role
from entitysdk.registration.classification import (
    register_etype_classification,
    register_mtype_classification,
)
from entitysdk.registration.memodel import register_memodel_calibration_result
from entitysdk.registration.validation_result import register_memodel_validation_results
from entitysdk.types import ID, ValidationStatus

from obi_one.scientific.tasks.memodel_build.config import MEModelBuildSingleConfig

L = logging.getLogger(__name__)

CREATOR_ROLE_NAME = "creator role"


def register_memodel(
    config: MEModelBuildSingleConfig,
    db_client: entitysdk.Client,
    *,
    authorized_public: bool,
) -> MEModel:
    """Register the ME-model alone, with ``validation_status=created``.

    ``entitysdk.registration.memodel.register_memodel`` is not used: it requires the holding
    and threshold currents, which are only known after calibration, and has no ``strain``.
    """
    morphology_ref = config.initialize.morphology
    morphology = morphology_ref.entity(db_client=db_client)
    emodel = config.initialize.emodel.entity(db_client=db_client)
    species, brain_region = morphology_ref.metadata_entities(db_client=db_client)

    memodel = db_client.register_entity(
        MEModel(
            name=config.info.campaign_name,
            description=config.info.campaign_description,
            morphology=morphology,
            emodel=emodel,
            species=species,
            # metadata_entities above raises when the morphology has no subject
            strain=morphology.subject.strain,  # ty:ignore[unresolved-attribute]
            brain_region=brain_region,
            validation_status=ValidationStatus.created,
            authorized_public=authorized_public,
        )
    )
    L.info("MEModel registered: %s", memodel.id)
    return memodel


def register_creator_and_classifications(
    config: MEModelBuildSingleConfig, db_client: entitysdk.Client, memodel: MEModel
) -> None:
    morphology = config.initialize.morphology.entity(db_client=db_client)
    emodel = config.initialize.emodel.entity(db_client=db_client)

    creator = db_client.search_entity(
        entity_type=Person, query={"sub_id": memodel.created_by.id}, limit=1
    ).one()
    creator_role = db_client.search_entity(
        entity_type=Role, query={"name": CREATOR_ROLE_NAME}, limit=1
    ).one()
    db_client.register_entity(Contribution(agent=creator, role=creator_role, entity=memodel))

    for mtype in morphology.mtypes or []:
        register_mtype_classification(client=db_client, entity=memodel, mtype_class=mtype)
    for etype in emodel.etypes or []:
        register_etype_classification(client=db_client, entity=memodel, etype_class=etype)


def register_calibration(
    db_client: entitysdk.Client, *, memodel_id: ID, calibration: dict, authorized_public: bool
) -> None:
    register_memodel_calibration_result(
        client=db_client,
        calibrated_entity_id=memodel_id,
        holding_current=calibration["holding_current"],
        threshold_current=calibration["rheobase"],
        rin=calibration.get("rin"),
        authorized_public=authorized_public,
    )


def register_validation(
    db_client: entitysdk.Client, *, memodel_id: ID, validation: dict, authorized_public: bool
) -> None:
    register_memodel_validation_results(
        client=db_client,
        memodel_id=memodel_id,
        validation_dict=validation,
        authorized_public=authorized_public,
    )


def set_validation_status(
    db_client: entitysdk.Client, *, memodel_id: ID, validation_status: ValidationStatus
) -> None:
    db_client.update_entity(
        entity_id=memodel_id,
        entity_type=MEModel,
        attrs_or_entity={"validation_status": validation_status},
    )
    L.info("MEModel %s validation_status: %s", memodel_id, validation_status)

from http import HTTPStatus
from typing import Annotated

import entitysdk.client
import entitysdk.exception
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.errors import ApiErrorCode
from obi_one.scientific.library.entity_property_types import IonChannelPropertyType
from obi_one.scientific.library.ion_channel_properties import get_ion_channel_variables
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.utils import (
    fetch_variable_catalog,
)

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


@router.get(
    "/mapped-ion-channel-properties",
    summary="Mapped ion channel properties",
    description="Returns a dictionary of mapped ion channel properties.",
)
def mapped_ion_channel_properties_endpoint(
    ion_channel_ids: Annotated[list[str], Query()],
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> dict:
    try:
        ion_channel_properties = get_ion_channel_variables(
            ion_channel_ids=ion_channel_ids,
            db_client=db_client,
        )
        mapped_ion_channel_properties = {}
        mapped_ion_channel_properties[IonChannelPropertyType.RECORDABLE_VARIABLES] = {
            key: value.variables for key, value in ion_channel_properties.items()
        }

    except entitysdk.exception.EntitySDKError as err:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": f"Internal error retrieving ion channel models among {ion_channel_ids}.",
            },
        ) from err

    return mapped_ion_channel_properties


@router.get(
    "/mapped-ion-channel-properties/emodel-optimization-variables",
    summary="Task 2 modifiable variable catalog",
    description=(
        "Returns the RANGE/GLOBAL/conductance variable catalog for selected IonChannelModel "
        "entities, using the same qualified-naming and RANGE-vs-GLOBAL placement rules as the "
        "EModel Optimization (Task 2) params compiler. UI clients configuring "
        "emodel_optimisation_parameters.mechanisms.mechanism_regions / global_parameters "
        "must use this endpoint instead of reading neuron_block directly, so channel-name "
        "qualification (e.g. "
        "'gNa' -> 'gNa_NaTg') cannot drift between the form and the compiler."
    ),
)
def emodel_optimization_variable_catalog_endpoint(
    ion_channel_ids: Annotated[list[str], Query()],
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> dict:
    try:
        catalog = fetch_variable_catalog(ion_channel_ids=ion_channel_ids, db_client=db_client)
    except entitysdk.exception.EntitySDKError as err:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": f"Internal error retrieving ion channel models among {ion_channel_ids}.",
            },
        ) from err

    return {
        entity_id: {
            "entity_id": model.entity_id,
            "name": model.name,
            "nmodl_suffix": model.nmodl_suffix,
            "is_stochastic": model.is_stochastic,
            "is_ljp_corrected": model.is_ljp_corrected,
            "temperature_celsius": model.temperature_celsius,
            "variables": [
                {
                    "name": variable.name,
                    "source_name": variable.source_name,
                    "units": variable.units,
                    "variable_type": variable.variable_type,
                    "allowed_group": "region" if variable.variable_type == "RANGE" else "global",
                }
                for variable in model.variables
            ],
        }
        for entity_id, model in catalog.items()
    }

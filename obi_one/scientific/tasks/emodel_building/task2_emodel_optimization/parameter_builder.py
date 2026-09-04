"""Resolve IonChannelModel entities and re-export BluePyEModel params compilation.

The params compiler and the IonChannelModel normalization live in
:mod:`bluepyemodel.preprocessing.parameters`. Only the EntityCore-bound lookups
stay here, because they need an ``entitysdk`` client.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bluepyemodel.preprocessing.morphology_preflight import MorphologyCapabilities
from bluepyemodel.preprocessing.parameters import (
    DEFAULT_BOUNDS_FALLBACKS,
    DEFAULT_SOMA_REF_LOCATION,
    REVERSAL_POTENTIAL_IONS,
    IonChannelVariable,
    NormalizedIonChannelModel,
    build_params_definition,
    normalize_ion_channel_model,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID


def resolve_ion_channel_models(
    references: Iterable[IonChannelModelFromID],
    db_client: Any,
) -> dict[str, NormalizedIonChannelModel]:
    """Resolve selected IonChannelModel references and normalize their metadata."""
    normalized: dict[str, NormalizedIonChannelModel] = {}
    for reference in references:
        normalized[reference.id_str] = normalize_ion_channel_model(
            reference.entity(db_client=db_client),
            entity_id=reference.id_str,
        )
    return normalized


def fetch_variable_catalog(
    ion_channel_ids: Iterable[str],
    db_client: Any,
) -> dict[str, NormalizedIonChannelModel]:
    """Fetch and normalize the RANGE/GLOBAL/conductance variable catalog for entities.

    UI clients must consume this catalog through the ``GET /declared/mapped-ion-channel-
    properties/emodel-optimization-variables`` endpoint rather than re-deriving qualified
    names from raw EntitySDK ``neuron_block`` data, so the ``gNa`` → ``gNa_NaTg`` naming
    rule cannot drift between the compiler and the form.

    Returns a mapping keyed by entity ID, matching the shape used internally by
    :func:`resolve_ion_channel_models`.
    """
    from entitysdk.models import IonChannelModel  # ruff: ignore[import-outside-top-level]

    catalog: dict[str, NormalizedIonChannelModel] = {}
    for ion_channel_id in ion_channel_ids:
        entity = db_client.get_entity(
            entity_id=ion_channel_id,
            entity_type=IonChannelModel,
        )
        catalog[str(ion_channel_id)] = normalize_ion_channel_model(
            entity,
            entity_id=str(ion_channel_id),
        )
    return catalog


__all__ = [
    "DEFAULT_BOUNDS_FALLBACKS",
    "DEFAULT_SOMA_REF_LOCATION",
    "REVERSAL_POTENTIAL_IONS",
    "IonChannelVariable",
    "MorphologyCapabilities",
    "NormalizedIonChannelModel",
    "build_params_definition",
    "fetch_variable_catalog",
    "normalize_ion_channel_model",
    "resolve_ion_channel_models",
]

"""eFEL features and generic protocol model.

A single generic :class:`EFeature` class represents any eFEL feature. The
:data:`EFEATURE_REGISTRY` maps every eFEL feature name to :class:`EFeature`.
:func:`get_feature_category` returns the category (Spike event, Spike shape,
Subthreshold) for any feature name.

The single :class:`Protocol` class (in :mod:`.protocols`) sources its valid
features from :func:`bluepyefe.ecode.get_valid_efeatures`.
"""

from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.efeatures import (  # noqa: E501
    EFEATURE_REGISTRY,
    EFeature,
    get_feature_category,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.protocols import (  # noqa: E501
    Protocol,
)

__all__ = [
    "EFEATURE_REGISTRY",
    "EFeature",
    "Protocol",
    "get_feature_category",
]

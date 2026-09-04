"""Runtime morphology capability checks for Task 2.

The preflight itself lives in :mod:`bluepyemodel.preprocessing.morphology_preflight`;
this module only re-exports it so Task 2 call sites stay stable.
"""

from bluepyemodel.preprocessing.morphology_preflight import (
    MorphologyCapabilities,
    load_morphology_nrn_order,
    preflight_morphology,
)

__all__ = [
    "MorphologyCapabilities",
    "load_morphology_nrn_order",
    "preflight_morphology",
]

"""Versioned artifacts for the launch-system EModel optimization consumer.

The compiler itself lives in :mod:`bluepyemodel.preprocessing`; this module only
re-exports it so Task 2 call sites and the contract paths stay stable.
"""

from bluepyemodel.preprocessing.artifacts import (
    TASK2_ARTIFACT_CONTRACT_VERSION,
    TASK2_CONFIG_CONTRACT_VERSION,
    build_optimization_artifacts,
)
from bluepyemodel.preprocessing.recipes import build_optimization_recipe
from bluepyemodel.preprocessing.schemas import (
    PARAMS_ARTIFACT_PATH,
    RECIPES_ARTIFACT_PATH,
    OptimizationArtifacts,
)

__all__ = [
    "PARAMS_ARTIFACT_PATH",
    "RECIPES_ARTIFACT_PATH",
    "TASK2_ARTIFACT_CONTRACT_VERSION",
    "TASK2_CONFIG_CONTRACT_VERSION",
    "OptimizationArtifacts",
    "build_optimization_artifacts",
    "build_optimization_recipe",
]

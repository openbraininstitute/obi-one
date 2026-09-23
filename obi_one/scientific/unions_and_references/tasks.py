from functools import reduce
from operator import or_
from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.tasks.basic_connectivity_plots import BasicConnectivityPlotsTask
from obi_one.scientific.tasks.circuit_extraction import CircuitExtractionTask
from obi_one.scientific.tasks.connectivity_matrix_extraction import ConnectivityMatrixExtractionTask
from obi_one.scientific.tasks.create_recording_array.create_recording_array import (
    CreateExtracellularRecordingArrayScanConfig,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
    EModelEFeatureExtractionTask,
)
from obi_one.scientific.tasks.ephys_extraction import ElectrophysiologyMetricsTask
from obi_one.scientific.tasks.folder_compression import FolderCompressionTask
from obi_one.scientific.tasks.generate_simulations.task.task import GenerateSimulationTask
from obi_one.scientific.tasks.ion_channel_modeling import IonChannelFittingTask
from obi_one.scientific.tasks.morphology_containerization import MorphologyContainerizationTask
from obi_one.scientific.tasks.morphology_decontainerization import MorphologyDecontainerizationTask
from obi_one.scientific.tasks.morphology_locations import MorphologyLocationsTask
from obi_one.scientific.tasks.morphology_metrics import MorphologyMetricsTask
from obi_one.scientific.tasks.skeletonization import SkeletonizationTask

try:
    # bluepyemodel (the "emodel" optional dependency group) is required to import Task 2's
    # Task class. Keep it out of this union rather than making `import obi_one` fail entirely
    # when the extra is not installed. See obi_one.scientific.mappings_and_registry.config_task_map
    # for the corresponding TASK_MAP registration guard.
    from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.task import (
        EModelOptimizationTask as _EModelOptimizationTask,
    )
except ImportError:
    _EModelOptimizationTask: type | None = None

_TASK_MEMBERS: tuple[type, ...] = (
    GenerateSimulationTask,
    CircuitExtractionTask,
    BasicConnectivityPlotsTask,
    ConnectivityMatrixExtractionTask,
    ElectrophysiologyMetricsTask,
    EModelEFeatureExtractionTask,
    FolderCompressionTask,
    IonChannelFittingTask,
    SkeletonizationTask,
    MorphologyContainerizationTask,
    MorphologyDecontainerizationTask,
    MorphologyMetricsTask,
    CreateExtracellularRecordingArrayScanConfig,
    MorphologyLocationsTask,
)
if _EModelOptimizationTask is not None:
    _TASK_MEMBERS = (*_TASK_MEMBERS, _EModelOptimizationTask)

TasksUnion = Annotated[
    reduce(or_, _TASK_MEMBERS),  # ty: ignore[invalid-type-form]
    Discriminator("type"),
]

from typing import ClassVar

from obi_one_lazy.scientific.tasks.simulation_execution.neuron.circuit_simulation_execution import (
    CircuitSimulationExecutionSingleConfig,
    CircuitSimulationExecutionTask,
)
from obi_one_lazy.types import TaskType


class SingleNeuronSynaptomeSimulationExecutionSingleConfig(CircuitSimulationExecutionSingleConfig):
    task_type: ClassVar[TaskType] = TaskType.single_neuron_synaptome_simulation_execution


class SingleNeuronSynaptomeSimulationExecutionTask(CircuitSimulationExecutionTask):
    pass

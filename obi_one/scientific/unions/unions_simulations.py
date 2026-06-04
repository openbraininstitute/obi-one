from obi_one.scientific.tasks.generate_simulations.config.brian2.brian2_circuit import (
    Brian2CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_ion_channel_models import (
    IonChannelModelSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model import (
    MEModelSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model_with_synapses import (  # noqa: E501
    MEModelWithSynapsesCircuitSimulationSingleConfig,
)

SIMULATION_GENERATION_SINGLE_CONFIGS = (
    CircuitSimulationSingleConfig
    | MEModelSimulationSingleConfig
    | MEModelWithSynapsesCircuitSimulationSingleConfig
    | IonChannelModelSimulationSingleConfig
    | Brian2CircuitSimulationSingleConfig
)

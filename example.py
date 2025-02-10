import obi

circuit_1 = obi.Circuit(circuit_path="circuit_1", node_set='hex0')
neuron_circuit_grouping_1 = obi.NeuronCircuitGrouping(circuit=circuit_1, neuron_ids=(1, 2, 3))
timestamps_1 = obi.RegularTimestamps(start_time=0.0, number_of_repetitions=1, interval=[1.0, 5.0])
stimulus_1 = obi.SynchronousSingleSpikeStimulus(spike_probability=[0.5, 0.8], timestamps=timestamps_1, circuit_grouping=neuron_circuit_grouping_1)
recording_1 = obi.Recording(start_time=0.0, end_time=1.0, circuit_grouping=neuron_circuit_grouping_1)

simulation_campaign = obi.SimulationCampaign(
                            template_simulation=obi.Simulation( circuit=circuit_1,
                                                                simulation_length=100,
                                                                circuit_groupings={"neuron_circuit_grouping_1": neuron_circuit_grouping_1},  
                                                                timestamps={"timestamps_1": timestamps_1}, 
                                                                stimuli={"stimulus_1": stimulus_1}, 
                                                                recordings={"recording_1": recording_1}))

# print(simulation_campaign.simulations)
simulation_campaign.write_simulation_sonata_configs("../simulation_configs/")




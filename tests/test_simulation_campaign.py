import obi_one as obi


def test_simulation_campaign():
    print("Testing Simulation Campaign... To be filled in later.")
    # circuit_path_prefix = "/Users/james/Documents/obi/additional_data/"

    # circuit = obi.Circuit(name="ToyCircuit-S1-6k", path=circuit_path_prefix + "ToyCircuit-S1-6k/circuit_config.json")
    # print(f"Circuit '{circuit}' with {circuit.sonata_circuit.nodes.size} neurons and {circuit.sonata_circuit.edges.size} synapses")

    # circuit2 = obi.Circuit(name="nbS1-HEX0-beta", path=circuit_path_prefix + "ToyCircuit-S1-6k/circuit_config.json")
    # print(f"Circuit '{circuit2}' with {circuit2.sonata_circuit.nodes.size} neurons and {circuit2.sonata_circuit.edges.size} synapses")

    # Simulation init
    # sim_neuron_set = obi.PredefinedNeuronSet(node_set="Layer1")
    # sim_duration = 3000.0  # ms
    # simulations_initialize = obi.SimulationsForm.Initialize(
    #     circuit=[circuit, circuit2],
    #     node_set=sim_neuron_set,
    #     simulation_length=sim_duration,
    # )

    # # Stimuli
    # stim_neuron_set = obi.PredefinedNeuronSet(node_set="Layer1", sample_percentage=[10, 20])
    # stim_times = obi.RegularTimestamps(
    #     start_time=0.0, number_of_repetitions=3, interval=1000.0
    # )  # in ms!!
    # current_stimulus = obi.ConstantCurrentClampSomaticStimulus(
    #     timestamps=stim_times, duration=5.0, neuron_set=stim_neuron_set, amplitude=[0.2, 0.5]
    # )
    # sync_current_stimulus = obi.ConstantCurrentClampSomaticStimulus(
    #     timestamps=stim_times, duration=100.0, neuron_set=stim_neuron_set, amplitude=0.1
    # )

    # # Recordings
    # rec_neuron_set = obi.PredefinedNeuronSet(node_set="Layer1", sample_percentage=100)
    # v_recording = obi.SomaVoltageRecording(
    #     start_time=0.0, end_time=sim_duration, neuron_set=rec_neuron_set
    # )

    # """
    # Fill form with Blocks
    # """
    # simulations_form = obi.SimulationsForm(
    #                                     initialize=simulations_initialize,
    #                                     intracellular_location_sets={},
    #                                     extracellular_location_sets={},
    #                                     neuron_sets={"L1All": sim_neuron_set, "L1Stim": stim_neuron_set, "L1Rec": rec_neuron_set},
    #                                     synapse_sets={},
    #                                     timestamps={"StimTimes": stim_times},
    #                                     stimuli={"CurrentStimulus": current_stimulus, "SyncCurrentStimulus": sync_current_stimulus},
    #                                     recordings={"SomaVoltRec": v_recording},
    #                                     )

    # simulations_form.model_dump(mode="json")

    # grid_scan_output_path = Path('../obi-output-tests/circuit_simulations/grid_scan')
    # if grid_scan_output_path.exists():
    #     grid_scan_output_path.rmdir()

    # grid_scan = obi.GridScan(form=simulations_form, output_root=grid_scan_output_path)
    # grid_scan.multiple_value_parameters(display=True)
    # grid_scan.coordinate_parameters(display=True)
    # grid_scan.coordinate_instances(display=True)
    # grid_scan.execute(processing_method='generate')

    # # Deserialization
    # grid_scan_ds = obi.deserialize_obi_object_from_json_file(grid_scan_output_path / "run_scan_config.json")

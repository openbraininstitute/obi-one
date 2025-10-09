import json
import re

import h5py
import numpy as np
import pytest
from bluepysnap import Simulation

import obi_one as obi

from tests.utils import CIRCUIT_DIR


def _setup_sim():
    circuit_list = [
        obi.Circuit(
            name="N_10__top_nodes_dim6",
            path=str(CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"),
        ),
        obi.Circuit(
            name="N_10__top_rc_nodes_dim2_rc",
            path=str(CIRCUIT_DIR / "N_10__top_rc_nodes_dim2_rc" / "circuit_config.json"),
        ),
    ]

    sim_duration = 3000.0
    sim_conf = obi.CircuitSimulationScanConfig.empty_config()
    info = obi.Info(campaign_name="Test", campaign_description="Test description")
    sim_conf.set(info, name="info")

    sim_neuron_set = obi.IDNeuronSet(
        neuron_ids=obi.NamedTuple(name="IDNeuronSet1", elements=range(10))
    )
    sim_conf.add(sim_neuron_set, name="ID10")

    sync_neuron_set = obi.IDNeuronSet(
        neuron_ids=obi.NamedTuple(name="IDNeuronSet2", elements=range(3))
    )
    sim_conf.add(sync_neuron_set, name="ID3")

    replay_neuron_set = obi.nbS1VPMInputs(sample_percentage=25)
    sim_conf.add(replay_neuron_set, name="VPM_input")

    regular_timestamps = obi.RegularTimestamps(
        start_time=0.0, number_of_repetitions=3, interval=1000.0
    )
    sim_conf.add(regular_timestamps, name="RegularTimestamps")

    poisson_input = obi.PoissonSpikeStimulus(
        duration=800.0,
        timestamps=regular_timestamps.ref,
        frequency=20,
        source_neuron_set=replay_neuron_set.ref,
        targeted_neuron_set=sim_neuron_set.ref,
    )
    sim_conf.add(poisson_input, name="PoissonInputStimulus")

    sync_input = obi.FullySynchronousSpikeStimulus(
        timestamps=regular_timestamps.ref,
        source_neuron_set=sync_neuron_set.ref,
        targeted_neuron_set=sim_neuron_set.ref,
    )
    sim_conf.add(sync_input, name="SynchronousInputStimulus")

    voltage_recording = obi.SomaVoltageRecording(
        neuron_set=sim_neuron_set.ref, start_time=0.0, end_time=sim_duration
    )
    sim_conf.add(voltage_recording, name="VoltageRecording")

    syn_manip_mg = obi.SynapticMgManipulation(magnesium_value=[2.0, 2.4])
    syn_manip_use = obi.ScaleAcetylcholineUSESynapticManipulation(use_scaling=0.7050728631217412)
    sim_conf.add(syn_manip_mg, name="SynapticMgManipulation")
    sim_conf.add(syn_manip_use, name="ScaleAcetylcholineUSESynapticManipulation")

    simulations_initialize = obi.CircuitSimulationScanConfig.Initialize(
        circuit=circuit_list, node_set=sim_neuron_set.ref, simulation_length=sim_duration
    )

    sim_conf.set(simulations_initialize, name="initialize")

    return sim_conf, sync_neuron_set, sim_neuron_set


def _check_generated_sims(tmp_path, scan):
    for instance in scan.single_configs:
        res_sim = Simulation(
            tmp_path / scan.output_root / str(instance.idx) / "simulation_config.json"
        )

        # Check circuit
        c_orig = instance.initialize.circuit.sonata_circuit
        assert c_orig.config == res_sim.circuit.config

        # Check node sets
        for nset in instance.neuron_sets:
            assert nset in res_sim.node_sets

        # Check spike files
        for key, stim in instance.stimuli.items():
            src = getattr(instance, stim.source_neuron_set.block_dict_name)[
                stim.source_neuron_set.block_name
            ]
            pop = src.get_population(instance.initialize.circuit.default_population_name)
            with h5py.File(
                tmp_path / scan.output_root / str(instance.idx) / (key + "_spikes.h5"), "r"
            ) as h5:
                nids = np.array(h5[f"spikes/{pop}/node_ids"])
                ts = np.array(h5[f"spikes/{pop}/timestamps"])
            assert len(nids) == len(ts)
            assert len(nids) > 0
            nids_orig = c_orig.nodes[pop].ids()
            assert np.all(np.isin(nids, nids_orig))
            tmin = np.min(instance.timestamps[stim.timestamps.block_name].timestamps())
            tmax = np.max(instance.timestamps[stim.timestamps.block_name].timestamps())
            assert np.all(ts >= tmin + stim.timestamp_offset)
            assert np.all(
                ts
                <= tmax
                + stim.timestamp_offset
                + (stim.duration if hasattr(stim, "duration") else 0.0)
            )


def _check_generated_sonata_configs(tmp_path, scan):
    for instance in scan.single_configs:
        cfg_file = tmp_path / scan.output_root / str(instance.idx) / "simulation_config.json"
        with cfg_file.open("r") as f:
            cfg = json.load(f)

        assert cfg.pop("version") == 2.4
        assert cfg.pop("target_simulator") == "NEURON"
        assert cfg.pop("run") == {"dt": 0.025, "random_seed": 1, "tstop": 3000.0}
        mech_dict = {
            "ProbAMPANMDA_EMS": {"init_depleted": True, "minis_single_vesicle": True},
            "ProbGABAAB_EMS": {"init_depleted": True, "minis_single_vesicle": True},
        }
        assert cfg.pop("conditions") == {
            "extracellular_calcium": 1.1,
            "v_init": -80.0,
            "spike_location": "soma",
            "mechanisms": mech_dict,
        }
        assert cfg.pop("network") == str(instance.initialize.circuit.path)
        assert cfg.pop("output") == {"output_dir": "output", "spikes_file": "spikes.h5"}
        poisson_dict = {
            "delay": 0.0,
            "duration": 3000.0,
            "node_set": "ID10",
            "module": "synapse_replay",
            "input_type": "spikes",
            "spike_file": "PoissonInputStimulus_spikes.h5",
        }
        sync_dict = {
            "delay": 0.0,
            "duration": 3000.0,
            "node_set": "ID10",
            "module": "synapse_replay",
            "input_type": "spikes",
            "spike_file": "SynchronousInputStimulus_spikes.h5",
        }
        assert cfg.pop("inputs") == {
            "PoissonInputStimulus": poisson_dict,
            "SynchronousInputStimulus": sync_dict,
        }
        volt_dict = {
            "cells": "ID10",
            "sections": "soma",
            "type": "compartment",
            "compartments": "center",
            "variable_name": "v",
            "unit": "mV",
            "dt": 0.1,
            "start_time": 0.0,
            "end_time": 3000.0,
        }
        assert cfg.pop("reports") == {"VoltageRecording": volt_dict}
        mg = instance.synaptic_manipulations["SynapticMgManipulation"].magnesium_value
        mg_dict = {
            "name": "Mg",
            "source": "All",
            "target": "All",
            "synapse_configure": f"%s.mg = {mg}",
        }
        use_dict = {
            "name": "ach_use",
            "source": "All",
            "target": "All",
            "synapse_configure": "%s.Use *= 0.7050728631217412",
        }
        assert cfg.pop("connection_overrides") == [mg_dict, use_dict]
        assert cfg.pop("node_set") == "ID10"
        assert cfg.pop("node_sets_file") == "node_sets.json"
        assert len(cfg) == 0  # No additional entries


def _check_generated_obi_config(tmp_path, scan):  # noqa: PLR0914
    cfg_file = tmp_path / scan.output_root / "run_scan_config.json"
    with cfg_file.open("r") as f:
        cfg = json.load(f)

    assert len(cfg.pop("obi_one_version")) > 0
    assert cfg.pop("type") == scan.type
    assert cfg.pop("output_root") == str(scan.output_root)
    ts_dict = {
        "type": "RegularTimestamps",
        "start_time": 0.0,
        "interval": 1000.0,
        "number_of_repetitions": 3,
    }
    ts_ref = {
        "block_dict_name": "timestamps",
        "block_name": "RegularTimestamps",
        "type": "TimestampsReference",
    }
    vpm_ref = {
        "block_dict_name": "neuron_sets",
        "block_name": "VPM_input",
        "type": "NeuronSetReference",
    }
    id3_ref = {"block_dict_name": "neuron_sets", "block_name": "ID3", "type": "NeuronSetReference"}
    id10_ref = {
        "block_dict_name": "neuron_sets",
        "block_name": "ID10",
        "type": "NeuronSetReference",
    }
    poisson_dict = {
        "type": "PoissonSpikeStimulus",
        "timestamps": ts_ref,
        "source_neuron_set": vpm_ref,
        "targeted_neuron_set": id10_ref,
        "timestamp_offset": 0.0,
        "duration": 800.0,
        "frequency": 20.0,
        "random_seed": 0,
    }
    sync_dict = {
        "type": "FullySynchronousSpikeStimulus",
        "timestamps": ts_ref,
        "source_neuron_set": id3_ref,
        "targeted_neuron_set": id10_ref,
        "timestamp_offset": 0.0,
    }
    volt_dict = {"type": "SomaVoltageRecording", "neuron_set": id10_ref, "dt": 0.1}
    id10 = {"name": "IDNeuronSet1", "elements": list(range(10)), "type": "NamedTuple"}
    id3 = {"name": "IDNeuronSet2", "elements": list(range(3)), "type": "NamedTuple"}
    id10_dict = {
        "type": "IDNeuronSet",
        "sample_percentage": 100.0,
        "sample_seed": 1,
        "neuron_ids": id10,
    }
    id3_dict = {
        "type": "IDNeuronSet",
        "sample_percentage": 100.0,
        "sample_seed": 1,
        "neuron_ids": id3,
    }
    vpm_dict = {"type": "nbS1VPMInputs", "sample_percentage": 25.0, "sample_seed": 1}
    mg = scan.form.synaptic_manipulations["SynapticMgManipulation"].magnesium_value
    mg_dict = {"type": "SynapticMgManipulation", "magnesium_value": mg}
    use_dict = {
        "type": "ScaleAcetylcholineUSESynapticManipulation",
        "use_scaling": 0.7050728631217412,
    }
    circuit_list = [
        {
            "name": scan.form.initialize.circuit[idx].name,
            "path": scan.form.initialize.circuit[idx].path,
            "matrix_path": None,
            "type": "Circuit",
        }
        for idx in range(2)
    ]
    init_dict = {
        "type": "CircuitSimulationScanConfig.Initialize",
        "circuit": circuit_list,
        "node_set": id10_ref,
        "simulation_length": 3000.0,
        "extracellular_calcium_concentration": 1.1,
        "v_init": -80.0,
        "random_seed": 1,
    }
    info_dict = {
        "type": "Info",
        "campaign_name": "Test",
        "campaign_description": "Test description",
    }
    form_dict = {
        "type": "CircuitSimulationScanConfig",
        "timestamps": {"RegularTimestamps": ts_dict},
        "stimuli": {"PoissonInputStimulus": poisson_dict, "SynchronousInputStimulus": sync_dict},
        "recordings": {"VoltageRecording": volt_dict},
        "neuron_sets": {
            "ID10": id10_dict,
            "ID3": id3_dict,
            "VPM_input": vpm_dict,
        },
        "synaptic_manipulations": {
            "SynapticMgManipulation": mg_dict,
            "ScaleAcetylcholineUSESynapticManipulation": use_dict,
        },
        "initialize": init_dict,
        "info": info_dict,
    }
    assert cfg.pop("form") == form_dict
    assert cfg.pop("coordinate_directory_option") == "ZERO_INDEX"
    assert len(cfg) == 0  # No additional entries


def _check_generated_instance_configs(tmp_path, scan):  # noqa: PLR0914
    for instance in scan.single_configs:
        cfg_file = tmp_path / scan.output_root / str(instance.idx) / "run_coordinate_instance.json"
        with cfg_file.open("r") as f:
            cfg = json.load(f)

        assert len(cfg.pop("obi_one_version")) > 0
        assert cfg.pop("type") == "CircuitSimulationSingleConfig"
        assert cfg.pop("idx") == instance.idx
        assert cfg.pop("coordinate_output_root") == str(scan.output_root / str(instance.idx))
        assert cfg.pop("scan_output_root") == str(scan.output_root)
        mg = instance.synaptic_manipulations["SynapticMgManipulation"].magnesium_value
        circuit_dict = {
            "name": instance.initialize.circuit.name,
            "path": str(instance.initialize.circuit.path),
            "matrix_path": None,
            "type": "Circuit",
        }
        scan_dict1 = {
            "location_list": [
                "synaptic_manipulations",
                "SynapticMgManipulation",
                "magnesium_value",
            ],
            "type": "SingleValueScanParam",
            "value": mg,
        }
        scan_dict2 = {
            "location_list": ["initialize", "circuit"],
            "type": "SingleValueScanParam",
            "value": circuit_dict,
        }
        assert cfg.pop("single_coordinate_scan_params") == {
            "scan_params": [scan_dict1, scan_dict2],
            "nested_coordinate_subpath_str": ".",
            "type": "SingleCoordinateScanParams",
        }
        ts_dict = {
            "type": "RegularTimestamps",
            "start_time": 0.0,
            "interval": 1000.0,
            "number_of_repetitions": 3,
        }
        assert cfg.pop("timestamps") == {"RegularTimestamps": ts_dict}
        ts_ref = {
            "block_dict_name": "timestamps",
            "block_name": "RegularTimestamps",
            "type": "TimestampsReference",
        }
        vpm_ref = {
            "block_dict_name": "neuron_sets",
            "block_name": "VPM_input",
            "type": "NeuronSetReference",
        }
        id3_ref = {
            "block_dict_name": "neuron_sets",
            "block_name": "ID3",
            "type": "NeuronSetReference",
        }
        id10_ref = {
            "block_dict_name": "neuron_sets",
            "block_name": "ID10",
            "type": "NeuronSetReference",
        }
        poisson_dict = {
            "type": "PoissonSpikeStimulus",
            "timestamps": ts_ref,
            "source_neuron_set": vpm_ref,
            "targeted_neuron_set": id10_ref,
            "timestamp_offset": 0.0,
            "duration": 800.0,
            "frequency": 20.0,
            "random_seed": 0,
        }
        sync_dict = {
            "type": "FullySynchronousSpikeStimulus",
            "timestamps": ts_ref,
            "source_neuron_set": id3_ref,
            "targeted_neuron_set": id10_ref,
            "timestamp_offset": 0.0,
        }
        assert cfg.pop("stimuli") == {
            "PoissonInputStimulus": poisson_dict,
            "SynchronousInputStimulus": sync_dict,
        }
        volt_dict = {"type": "SomaVoltageRecording", "neuron_set": id10_ref, "dt": 0.1}
        assert cfg.pop("recordings") == {"VoltageRecording": volt_dict}
        id10 = {"name": "IDNeuronSet1", "elements": list(range(10)), "type": "NamedTuple"}
        id3 = {"name": "IDNeuronSet2", "elements": list(range(3)), "type": "NamedTuple"}
        id10_dict = {
            "type": "IDNeuronSet",
            "sample_percentage": 100.0,
            "sample_seed": 1,
            "neuron_ids": id10,
        }
        id3_dict = {
            "type": "IDNeuronSet",
            "sample_percentage": 100.0,
            "sample_seed": 1,
            "neuron_ids": id3,
        }
        vpm_dict = {"type": "nbS1VPMInputs", "sample_percentage": 25.0, "sample_seed": 1}
        assert cfg.pop("neuron_sets") == {
            "ID10": id10_dict,
            "ID3": id3_dict,
            "VPM_input": vpm_dict,
        }
        mg_dict = {"type": "SynapticMgManipulation", "magnesium_value": mg}
        use_dict = {
            "type": "ScaleAcetylcholineUSESynapticManipulation",
            "use_scaling": 0.7050728631217412,
        }
        assert cfg.pop("synaptic_manipulations") == {
            "SynapticMgManipulation": mg_dict,
            "ScaleAcetylcholineUSESynapticManipulation": use_dict,
        }
        init_dict = {
            "type": "CircuitSimulationScanConfig.Initialize",
            "circuit": circuit_dict,
            "node_set": id10_ref,
            "simulation_length": 3000.0,
            "extracellular_calcium_concentration": 1.1,
            "v_init": -80.0,
            "random_seed": 1,
        }
        assert cfg.pop("initialize") == init_dict
        info_dict = {
            "type": "Info",
            "campaign_name": "Test",
            "campaign_description": "Test description",
        }
        assert cfg.pop("info") == info_dict
        assert len(cfg) == 0  # No additional entries


def test_simulation_campaign_generation(tmp_path):
    # Set up simulation campaign
    sim_conf, sync_neuron_set, sim_neuron_set = _setup_sim()

    # Validated config
    validated_sim_conf = sim_conf.validated_config()

    # Generate a grid scan
    grid_scan = obi.GridScanGenerationTask(
        form=validated_sim_conf,
        output_root=tmp_path / "grid_scan",
        coordinate_directory_option="ZERO_INDEX",
    )
    assert len(grid_scan.multiple_value_parameters()) == 2
    assert len(grid_scan.coordinate_parameters()) == 4
    grid_scan.execute()
    obi.run_tasks_for_generated_scan(grid_scan)

    _check_generated_sims(tmp_path, grid_scan)
    _check_generated_sonata_configs(tmp_path, grid_scan)
    _check_generated_obi_config(tmp_path, grid_scan)
    _check_generated_instance_configs(tmp_path, grid_scan)

    # Run again --> Error
    with pytest.raises(
        ValueError, match=r"Output file '.*' already exists! Delete or choose to overwrite."
    ):
        obi.run_tasks_for_generated_scan(grid_scan)

    # Generate a coupled coordinate scan
    coupled_scan = obi.CoupledScanGenerationTask(
        form=validated_sim_conf,
        output_root=tmp_path / "coupled_scan",
        coordinate_directory_option="ZERO_INDEX",
    )
    assert len(coupled_scan.multiple_value_parameters()) == 2
    assert len(coupled_scan.coordinate_parameters()) == 2
    coupled_scan.execute()
    obi.run_tasks_for_generated_scan(coupled_scan)

    _check_generated_sims(tmp_path, coupled_scan)
    _check_generated_sonata_configs(tmp_path, coupled_scan)
    _check_generated_obi_config(tmp_path, coupled_scan)
    _check_generated_instance_configs(tmp_path, coupled_scan)

    # Run again --> Error
    with pytest.raises(
        ValueError, match=r"Output file '.*' already exists! Delete or choose to overwrite."
    ):
        obi.run_tasks_for_generated_scan(coupled_scan)

    # Use a neuron set reference without adding it to the simulation config --> Error
    sim_neuron_set2 = obi.IDNeuronSet(
        neuron_ids=obi.NamedTuple(name="IDNeuronSet3", elements=range(5))
    )
    with pytest.raises(ValueError, match=re.escape("Block reference has not been set.")):
        _ = obi.SomaVoltageRecording(
            neuron_set=sim_neuron_set2.ref,
            start_time=0.0,
            end_time=sim_conf.initialize.simulation_length,
        )

    # Use a time stamp reference without adding it to the simulation config --> Error
    regular_timestamps2 = obi.RegularTimestamps(
        start_time=0.0, number_of_repetitions=5, interval=1000.0
    )
    with pytest.raises(ValueError, match=re.escape("Block reference has not been set.")):
        _ = obi.FullySynchronousSpikeStimulus(
            timestamps=regular_timestamps2.ref,
            source_neuron_set=sync_neuron_set.ref,
            targeted_neuron_set=sim_neuron_set.ref,
        )

    # Use different numbers of coordinates in coupled scan --> Error
    sim_conf.synaptic_manipulations["SynapticMgManipulation"].magnesium_value = [2.0, 2.4, 2.8]
    validated_sim_conf = sim_conf.validated_config()
    coupled_scan2 = obi.CoupledScanGenerationTask(
        form=validated_sim_conf,
        output_root=tmp_path / "coupled_scan_err",
        coordinate_directory_option="ZERO_INDEX",
    )
    with pytest.raises(ValueError, match="Multi value parameters have different lengths:"):
        coupled_scan2.execute()

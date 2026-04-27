def add_relative_ou_stimulus(config, name, node_set, mean, sd, delay, duration, reversal=0, tau=2.7):

    config['inputs'][name] = {
            "input_type": "conductance",
            "module": "relative_ornstein_uhlenbeck",
            "delay": delay,
            "duration": duration,
            "reversal": reversal,
            "tau": tau,
            "mean_percent": mean,
            "sd_percent": sd,
            "node_set": node_set
        }
    
def add_spike_replay(config, name, sim_length, spike_file, source, delay=0):
    config["inputs"]["Stimulus spikeReplay " + name] = {
            "module": "synapse_replay",
            "input_type": "spikes",
            "delay": delay,
            "duration": sim_length,
            "spike_file": spike_file,
            "source": source,
            "node_set": "hex_O1"
        }
    
def add_soma_reports(config, sim_length, dt=1.0, start_time=0):
  config["reports"] = {
      "Report soma": {
        "cells": "hex_O1",
        "sections": "soma",
        "type": "compartment",
        "compartments": "center",
        "variable_name": "v",
        "unit": "mV",
        "dt": dt,
        "start_time": start_time,
        "end_time": sim_length
      }
    }
  
def add_connection_overrides(config):
    config["connection_overrides"] = [
            {
                "name": "no_vpm_proj",
                "source": "proj_Thalamocortical_VPM_Source",
                "target": "hex_O1",
                "spontMinis": 0.0,
                "weight": 1.0
            },
            {
                "name": "no_pom_proj",
                "source": "proj_Thalamocortical_POM_Source",
                "target": "hex_O1",
                "spontMinis": 0.0,
                "weight": 1.0
            },
            {
                "name": "init",
                "source": "hex_O1",
                "target": "hex_O1",
                "weight": 1.0
            },
            {
                "name": "disconnect",
                "source": "hex_O1",
                "target": "hex_O1",
                "delay": 0.025,
                "weight": 0.0
            },
            {
                "name": "reconnect",
                "source": "hex_O1",
                "target": "hex_O1",
                "delay": 1000,
                "weight": 1.0
            }
        ]
    
def add_conditions(config, ca_conc):

    config["conditions"] = {
        "extracellular_calcium": ca_conc,
        "v_init": -80.0,
        "mechanisms": {
            "ProbAMPANMDA_EMS": {
                "init_depleted": True,
                "minis_single_vesicle": True
            },
            "ProbGABAAB_EMS": {
                "init_depleted": True,
                "minis_single_vesicle": True
            }
        }
    }
# Running Small Microcircuit Simulation using OBI-One and BlueCellulab
Darshan Mandge
June 2025

## Overview

The folder has a 
- A Notebook `run_small_microcircuit.ipynb` to run a small microcircuit simulation using OBI-One via BlueCellulab. 
- A shell script `run_small_microcircuit.sh` to run a small microcircuit simulation directly using BlueCellulab.
    - This script calls `run_circuit_bluecellulab.py`.
    - The shell script compiles the NEURON mod files, runs the simulation parallelly using MPI, and saves the results the `output` folder in the circuit directory: 
        - SONATA spike and soma reports files (.h5).
        - an NWB file.
        - a plot of voltage traces for all simulated cells.
    - The input to the script is a SONATA circuit `simulation_config.json` file.
    



## Prerequisites

- Python >= 3.9
- BlueCellulab >= 2.6.59
- NEURON >= 8.0
- matplotlib
- bluepysnap
- h5py    

# Running Small Microcircuit Simulation using OBI-One and BlueCellulab
Darshan Mandge
28th June 2025

## Overview

The example folder `run_small_microcircuit` has:

- A Notebook `run_small_microcircuit.ipynb` to run a small microcircuit simulation using [obi-one](https://github.com/openbraininstitute/obi-one) via [BlueCellulab](https://github.com/openbraininstitute/BlueCelluLab).

- A shell script `run_small_microcircuit.sh` to run a small microcircuit simulation directly using BlueCellulab.
    - This script calls `run_circuit_bluecellulab.py`.
    - The shell script compiles the NEURON mod files, runs the simulation parallelly using MPI and saves the results as:
        - SONATA spike and soma reports files,
        - an NWB file,
        - a plot of voltage traces for all simulated cells.
    - The input to the script is a SONATA circuit `simulation_config.json` file.
    - As the simulation config runs a spike replay using a H5 file, the shell script also copies the H5 file containing folder `input` from the circuit directory to the the script directory.

- This `README.md` file to explain the example.

- The spike replay file in `input` folder: `spike_replay.h5`.

## Output

The shell script saves the results in the `output` folder in the circuit directory:
- SONATA spike (out.h5) and soma reports files (SomaVoltRec.h5). The names of the files are as per the simulation config.
- an NWB file (`results.nwb`).
- a plot of voltage traces for all simulated cells (`voltage_traces.png`).
- a log file (`simulation_{timestamp}.log`), where `{timestamp}` is the current date and time. (e.g. `simulation_20250628_154149.log`).

## Running the shell script

- You can run a SONATA circuit using obi-one via BlueCellulab using the notebook `run_small_microcircuit.ipynb`. It uses a SONATA simulation config file `simulation_config.json`.

- To run simulation directly using BlueCellulab using the shell script, use the following command:`./run_small_microcircuit.sh`

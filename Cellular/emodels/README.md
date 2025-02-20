# E-model Experiments

Authors: Darshan Mandge, Aurélien Jaquier and Ilkan Kilic @ Open Brain Institute

Copyright (c) 2025 Open Brain Institute

Last Modified: 02.2025

This folder contains notebooks to perform several experiments on the electrical models (e-models) from the Open Brain Platform.

E-model resources required to run these notebooks
- e-model `hoc` file 
- morphology file (`.swc` or `.asc`) and 
- mechanisms (`.mod` files)
- EModel resource `json` (`EM_*.json`) with final parameters of the e-model (only for [parameter_plots notebook](parameters_plot/analysis_notebook.ipynb)).

These could be downloaded from 
- the [Open Brain Platform](https://openbraininstitute.org) from `Explore` -->`E-model` section --> Click on an e-model from the list --> `Download`. This final parameters file `EM_*.json` of the e-model.
- [Blue Brain Open Data](https://registry.opendata.aws/bluebrain_opendata/) using [Amazon CLI](https://aws.amazon.com/cli/) 
- (temporary for testing purpose) the data for below notebooks is also save [here](https://openbraininstitute.sharepoint.com/:f:/s/OBI-Scientificstaff/EpqQOMfkUoRIv5mkPmaTdWEBuVeg6qEi93fJbmy-FSsgRA?e=SwGY4V) in a private folder.

Here is brief introduction of each experiment

- [**`Optimised Parameter Comaprison Plot`**](parameters_plot/analysis_notebook.ipynb):
    - Compare parameters of an e-model across sections on Open Brain Institute Platform (OBP)
    - This notebook uses the final e-model paramters stored in EM__*.json file and compare the optimised paramters for different sections of the neuron e-model
    - We show a `scatter plot` and `heatmap` of parameters accross sections
    - The pipeline store the final e-model details in a json file  containing details such as
        - `fitness`  : the e-model score (sum of e-feature z-scores)
        - `parameter`: the hall of fame (best) parameters values which are were selected for different sections of the detailed morphology.  
        - `score`    : individual e-feature z-scores
        - `features` : individual e-feature absolute values
        - `scoreValidation` : validation score
        - `passedValidation`(bool) : passed or failed validation
        - `seed` : selected seed value from the multiple optimisation runs


- [**`cADpyr E-model Showcase`**](cadpyr_showcase/analysis_notebook.ipynb)
    - Demonstrates various properties of the OBP canonical cADPyr (continuos firing and adapting type pyramidal neuron) e-model including
        - `optimisation protocol response plots`
        - [`currentscape`](https://github.com/openbraininstitute/Currentscape) analysis
        - `Frequency-Current (F-I)` curve
        - `Current-Voltage (V-I)` curve
        - `recordings` in different sections of the neuron using [BlueCellulab](https://github.com/openbraininstitute/BlueCelluLab)
        - `dendritic potential decay` 
        - backpropagating action potential (`bAP`) recordings
        - excitatory postsynaptic potential(`EPSP`) recordings and `EPSP ratio`.

- [**`FI and IV Curve`**](plot_iv_fi_curve/analysis_notebook.ipynb)
    - Computes and visualize FI (frequency-current) and IV (current-voltage) curves for an e-model using BlueCelluLab.
    - FI Curve: 
        - Suprathreshold step current protocols are applied in e-model and 
        - We record and plot the action potential frequencies for different current amplitudes
    - IV Curve: 
        - Subthreshold step current protocols are injected
        - We record and plot steady-state potentials

- [**`Currentscape Analysis`**](single_cell_currentscape_analysis/analysis_notebook.ipynb) 
    - Currentscape analysis of an e-model
    - For a given stimulus protocol, the underlying ionic currents and concetrations are recorded and relative values are plotted with different colours

- [**`Impedance Analysis`**](single_cell_impedance_analysis/analysis_notebook.ipynb)
    - Impedance analysis of an e-model
    - A sinusoidal (chirp/ZAP) subthreshold current stimulus is injected into an e-model
    - We record the membrane potential (Vm) and normalised impedance (Z)

- **`Local Field Potential(LFP) Simulations`**  

    - [**`Passive e-model with synapse: Plot LFP Heatmap`**](lfpy_simulations/passive_emodel_synapses_heatmap/analysis_notebook.ipynb)
        - Running a passive OBP e-model with a synapse activation using [LFPy](https://github.com/LFPy/LFPy)
        - Plot LFP Heatmap recorded with a linear electrode array

    - [**`Passive e-model with synapse: Plot LFP`**](lfpy_simulations/passive_emodel_synapses_LFP/analysis_notebook.ipynb) 
        - Running a passive OBP e-model with a synapse activation
        - We record the LFP at different distances from the neuron in space (with spherical coordinates)

    - [**`Active e-model with IClamp: Plot LFP from MEA`**](lfpy_simulations/active_emodel_Iclamp/analysis_notebook.ipynb)
        - Running an OBP e-model with current clamp
        - We record and plot LFP on a microelectrode array (MEA)

    - [**`Active e-model with Synapse`e**](lfpy_simulations/active_emodel_synapses/analysis_notebook.ipynb) 
        - Running an OBP active e-model with a synapse activation using LFPy
        - Plot the intrtacellular synaptic current and intracellular potential
    
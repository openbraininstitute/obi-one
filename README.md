# obi_platform_analysis_notebooks
OBI Platform Analysis Notebooks

## Notebook Folder Structure

The folder has been divided into 3 main subfolders, each corresponding to the level of analysis: 

- **Cellular**
  - **analyse_single_cell_sim**: Notebooks to analyse single cell simulations
    - [**analyse_single_cell_sim**](Cellular/analyse_single_cell_sim/analysis_notebook.ipynb): Plot recordings and extract spikecount

  - **efeature_extraction**: Notebooks of e-feature extraction
    - [**current_clamp_ephys_extraction**](Cellular/efeature_extraction/current_clamp_ephys_extraction/analysis_notebook.ipynb): Extraction of e-features from voltage clamp experiments for analysing the firing behaviour of neurons, AP properties, subthreshold and suprathreshold voltage properties
    - [**voltage_clamp_ephys_extraction**](Cellular/efeature_extraction/voltage_clamp_ephys_extraction/analysis_notebook.ipynb): Extraction e-features from whole cell patch voltage clamp data. Use for ion channel model building.

  - **emodels**: Notebooks on E-models. See this [README](Cellular/emodels/README.md) for more details
      - [**parameter_plots**](Cellular/emodels/parameters_plot/analysis_notebook.ipynb): Compare parameters of an e-model across sections on Open Brain Institute Platform (OBP)
      - [**cadpyr_showcase**](Cellular/emodels/cadpyr_showcase/analysis_notebook.ipynb): Demonstrates various properties of the OBP canonical cADPyr (continuos firing and adapting type pyramidal neuron) e-model
      - [**plot_iv_fi_curve**](Cellular/emodels/plot_iv_fi_curve/analysis_notebook.ipynb): Computes and visualize IV and FI curves for a single-cell model using BlueCelluLab.
      - [**single_cell_currentscape_analysis**](Cellular/emodels/single_cell_currentscape_analysis/analysis_notebook.ipynb): Currentscape analysis of single cells
      - [**single_cell_impedance_analysis**](Cellular/emodels/single_cell_impedance_analysis/analysis_notebook.ipynb): Impedance analysis of single cells
      - **lfpy_simulations**
        - [**LFPy_active_iclamp**](Cellular/emodels/lfpy_simulations/active_emodel_Iclamp/analysis_notebook.ipynb): Running an OBP e-model with current clamp: record and plot LFP on a microelectrode array
        - [**LFPy_active_synapse**](Cellular/emodels/lfpy_simulations/active_emodel_synapses/analysis_notebook.ipynb): Running an OBP active e-model with a synapse activation
        - [**LFPy_passive_synapse_1**](Cellular/emodels/lfpy_simulations/passive_emodel_synapses/analysis_notebook_1.ipynb): Running a passive OBP e-model with a synapse activation: Plot LFP Heatmap
        - [**LFPy_passive_synapse_2**](Cellular/emodels/lfpy_simulations/passive_emodel_synapses/analysis_notebook_2.ipynb): Running a passive OBP e-model with a synapse activation: Plot Local Field

  - **morphologies**: Notebooks on morphologies
    - [**display_morphology_population_features**](Cellular/morphologies/display_morphology_population_features/analysis_notebook.ipynb): Plot morphological features for a population of morphologies
    - [**morphology_quality_check**](Cellular/morphologies/morphology_quality_check/analysis_notebook.ipynb): To test a list of morphologies against some common issues that may cause issues with tools and analyses using the morphologies.
      
- **Circuit**
  - [**adjacency_matrix**](Circuit/adjacency_matrix/analysis_notebook.ipynb): extracts and visualize the connectivity between all pairs of pre- and post-synaptic neurons
  - [**circuit_composition**](Circuit/circuit_composition/analysis_notebook.ipynb): displays the composition of a circuit model with respect to user-selected neuron properties, such as morphological types, electrical types, etc.
  - [**connectivity_matrix**](Circuit/connectivity_matrix/analysis_notebook.ipynb): extracts and visualizes a matrix of connection probabilities or #synapses per connection (mean/std/...), grouped by a selected neuron property (layer, m-type, ...).
  - [**synapse_properties_matrix**](Circuit/synapse_properties_matrix/analysis_notebook.ipynb):  analyse, extract and visualize a matrix of a selected synapse property (conductance, delay, ...), grouped by a selected neuron property (layer, m-type, ...).


- **Metabolism**
   - [**Metabolism**](Metabolism/analysis_notebook.ipynb): Data-driven molecular model of the neuro-glia-vascular system allows exploration of the complex relationships between the aging brain, energy metabolism, blood flow, and neuronal activity.

=========================================

Copyright (c) 2025 - Open Brain Institute
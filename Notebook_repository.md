# OBI notebook repository structure

This document describes the structure of jupyter notebooks to be used in an OBI virtual lab and of code repositories containing them.
In case of questions, it may be helpful to visit the [repository of official OBI notebooks](https://github.com/openbraininstitute/obi_platform_analysis_notebooks/tree/main) that adheres to these specifications.

## Repository structure
A notebook repository contains any number of the following folders:
 - Metabolism
 - Cellular
 - Circuit
 - System

The folders denote the scientific scale the notebooks are to be used for, e.g., subcellular and cellular metabolism, single (or paired) cell activity, microcircuit activity or the systems level. If no notebooks of a given level exist in a repository, the corresponding folder does not have to exist.

Within these folders, any number of notebooks can be added, but each in its individual subfolder. That subfolder can have any name, but by convention it should be provide an idea of the purpose of the notebook, and be all lower case with underscores separating words. 

Within the subfolder, three files are required:
 - README.md: A file that provides information about the purpose of the notebook and how it is used.
 - analysis_notebook.ipynb: The notebook itself. Note that it must have that specific name.
 - analysis_info.json: A json file that provides technical information about the notebook and how it is to be displayed in your virtual lab (see below).

 ## Notebook info
 The analysis_info.json must contain the following keys:
 - “name": Descriptive name, ideally 3-6 words with first letter capital and rest all small, except in special cases. 
 - “scale”: Scale of the analysis. This is the same as the root folder the notebook is in (Metabolism, Cellular, etc. See above), but all lower case. 
 - “authors”: List of authors, e.g., [“OBI”, “Another Name”]. 
 - "description”: A brief description of the notebook. Will be used to describe the notebook in your virtual lab. 
 - “type”: Value is always “notebook”. In the future, other types may be supported.
 - "kernel" (optional): The language of the kernel to run the notebook. If not provided, "python" is assumed.
 - “requirements”: A list of strings. Each string specifies a package and version requirement, i.e., like the individual lines of a requiremens.txt file. 
 - “input”: The expected inputs into the analysis performed in the notebook. The purpose of a notebook is to load in one or several artefact(s) of the types supported by the OBI platform and perform an analysis. This specifies the type expected. Value is a list of dicts. Each entry is one expected input. Each input is specified with the following keys: 
    - “class”: Value is one of “list” or “single”. If “list”, the notebook can analyze a population of a type of artefact together. If “single”, only a single one is analyzed in the notebook. 
    - “data_type”: Specifies what type of artefact that can be analyzed. A dict with two keys: 
         - “artefact”: The type of artefact. Must be one of the types listed below.
         - “required_properties”: A list of additional key-value pairs of properties that need to be fulfilled. For example, an analysis may only work for excitatory neurons. In that case: {"synapse_class": "excitatory"}.

## Notebook contents
A notebook can contain virtually any analysis. It is expected to begin by loading in the artefact(s) it is analyzing. The artefact(s) to be loaded is expected to be formatted in the way the "download" functionality of the "explore" section of the OBI platform provides. That is, as if one selects the artefact in "explore", uses the "download" button and places the downloaded file in the folder containing the notebook.

## List of artefact types:
- "CellMorphology": A reconstructed morphology. In skeleton representation. Format is one of .h5, .swc, .asc
- "ElectricalCellRecording": Experimental or simulated single cell recording in .nwb format.
- "ElectricalCellPairRecording": As above, but for a pair of (connected) neurons.
- "ElectricalCellModel": A parameterized model of the distribution of ion channels over the neuron membrane, plus those ion channel models. .json format.
- "ElectricalCellFeatures": "Features" of the electrical activity of a neuron upon standardized stimulation, such as AP height, width, etc.
- "IonChannelModel": A model of the kinetics of a class of ion channels. Format is .mod.
- "SynapseModel": A model of the kinetics of a synaptic contact. Format is .mod.
- "SingleCellSimulation": The result of a platform simulation of a single or paired neuron.
- "IonChannelModel": A computational model of the kinetics of a type of ion channel
- "SimulatableNeuron": A computational model of a single cell with morphology and electrophysiology that can be simulated.
- "SimulatableNeuronPair": As above, but for a pair of connected neurons. Contains references to the individual neurons and a synaptome of the connection(s) between them.
- "Synaptome": A set of synapses in a model of single neurons or a circuit. Can contain extrinsic synapses. In SONATA format, plus a reference to "SynapseModels" to be used.  
- "NeuronDensityAtlas": A voxel atlas of neuron densities for a given type of neuron. format: .nrrd
- "SimulatableCircuit": A SONATA formatted circuit model.
- "AnnotationAtlas": A voxel atlas that assigns region ids to each voxel.
- "ConnectivityMatrix": The adjacency matrix of a circuit at cellular resolution. Experimental or model. Format: .h5 format specified by the Connectome-Utilities python package.
- "emodel": A model describing the distribution of ion channels over the membrane of a neuron. Determines the electrical behavior of a neuron.
- "CircuitSimulation": The result of a platform simulation of a circuit model.
- "CircuitSimulationCampaign": As above, but for a full simulation campaign.

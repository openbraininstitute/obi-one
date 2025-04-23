# Run a Single Cell Simualtion using a SONATA circuit in OBI-ONE
Copyright (c) 2025 Open Brain Institute

Author: Darshan Mandge and Ilkan Kiliç, Open Brain Institute

Last Modified: 04.2025

## Summary
This simualtion
The example shows how you can:
1. Create a SONATA circuit structure for a single cell model
2. Run a simulation with the circuit using [BlueCellulab](https://github.com/openbraininstitute/BlueCelluLab)

## Use
### Download singlecell model files from Blue Brain Open Data
We will use the singlecell model from the [Blue Brain Open Data](https://registry.opendata.aws/bluebrain_opendata/). These models are registered on the [Open Brain Platform](https://www.openbraininstitute.org/). We will later integrate the example to run simulations via obi-one.

(For the ease of user, the following steps have been already run for this example)
The following script downloads the emodel files from Blue Brain Open Data and saved them in the respective `components` of folder needed for running the sonata simulations. 

Go to the home directory of the example and run 
 
`./create_sonata.sh`

This will:
- download the model from Blue Brain Open Data 
- create a SONATA nodes file (via `create_nodes_file.py`) by adding template and morphology data along with calcualting holding and threshold current  (via `calculate_threshold_holding.py`)
- arange the files in the following structure under `components` folder:

```
components/
├── mechanisms/
│   └── *.mod files     # ionic mechanisms
├── morphologies/
│   └── *.asc or *.swc  # morphology file
├── hoc/
│   └── cell_model.hoc  # hoc file used by 
├── network/
│   └── nodes.h5
├── EM_*.json
│  
├── node_sets.json
├── simulation_config.json
├── circuit_config.json
```

The `node_sets.json`, `simulation_config.json` and `circuit_config.json` are not generated and have to be created by the user. Please folllow the SOANTA documentation [here](https://sonata-extension.readthedocs.io/en/latest/sonata_overview.html). We also have an example for such files in [BlueCellulab](https://github.com/openbraininstitute/BlueCelluLab/tree/main/examples/2-sonata-network) to help you get started.


### Run a simulation with SONATA circuit

Open the `run_sonata_sim.ipynb` notebook and run it. This will plot the model response for the Ornstein-Uhlenbeck noise stimulus.

This `analysis_info.json` has the details of pacakges you would need to run the notebook.





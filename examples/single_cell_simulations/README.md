# Run a Single Cell Simualtion using a SONATA circuit in OBI-ONE
Copyright (c) 2025 Open Brain Institute

Author: Darshan Mandge, Open Brain Institute

Last Modified: 04.2025 (WIP)

## Summary
Create an example of single-cell simulation to run using a SONATA circuit file.

## Use
### Download e-model files from Blue Brain Open Data
`./download_model_aws.sh`
- add code to copy the model files to respective `components` folder

### Calculating the threshold and holding current of the EModel
`nrnivmodl components/mechanisms`
`python calculate_threhsold_holding.py`

### Create a nodes file
`python create_nodes_file.py`

### create a node_set file


To Ask
h5 file struc ture
Edge file? 






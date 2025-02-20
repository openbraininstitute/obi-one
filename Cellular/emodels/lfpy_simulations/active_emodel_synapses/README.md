# LFPy: active e-model synapses

Copyright (c) 2025 Open Brain Institute

Author: Darshan Mandge, Open Brain Institute

Last Modified: 02.2025

## Summary
In this notebook, we inject a step current in soma of the an e-model and record the local field potentials on a microelectrode array (MEA).

## Use
Follow the instructions in the notebook.

If you want to use a custom synapse, copy the mod file in the mechanisms directory and update the `syntype` in the below code with the POINT_PROCESS name of your synapse mod file.

Download the e-model folder from [here](https://openbraininstitute.sharepoint.com/:f:/s/OBI-Scientificstaff/Ei3QIGh3JFFHkRkY7LRyTpEBm8eUll7HGyusulkPavf5SA?e=7ihV8H) in OneDrive `OBI -> Scientific staff -> Documents -> Data -> Analysis notebook data -> cadpyr_emodel`

For this example, the downloaded folder `cadpyr_emodel` is kept here `./Cellular/emodels` of this repository

Please update the `emodel_path` variable with the path to the downloaded folder.
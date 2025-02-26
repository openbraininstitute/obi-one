# Parameter comparison plots among section of an e-model 

Author: Darshan Mandge, Open Brain Institute

Copyright (c) 2025 Open Brain Institute

Last Modified: 02.2025

## Summary
Notebook to compare final parameter values for different sections such as apical, basal dendrites and soma of a single cell electrical model (e-model).

## Details
- The goal of this notebook is to compare and understand the relation between different paramteres in an e-model
- An e-model is usually constructed from intracellular patch clamp data using multi-objective optimisation
- We use the Open Brain Institute (OBI) Platform and our single cell modelling pipeline: [BluePyEModel](https://github.com/openbraininstitute/BluePyEModel)
- The pipeline performs the following steps:
    - extraction of electrical features (e-features) from the electrophysiology data
    - optimisation of the e-features to minimise the z-score of each feature and reduce the overall
    e-model score (sum of e-feature z-scores) 
    - validate the model
- The pipeline store the final e-model details in a json file (EM__*.json) containing details such as
- `fitness`  : the e-model score (sum of e-feature z-scores)
- `parameter`: the hall of fame (best) parameters values which are were selected for different sections of the detailed morphology.  
- `score`    : individual e-feature z-scores
- `features` : individual e-feature absolute values
- `scoreValidation` : validation score
- `passedValidation`(bool) : passed or failed validation
- `seed` : selected seed value from the multiple optimisation runs

## Use

### Get the data
To plot your own, model, replace the `em_file` variable with the path to the downloaded `EM__*.json` file for an e-model from Open Brain Platform (OBP). 

To get a `EM__*.json` file from OBP, go to any e-model page on the platform and click download. It will download a download.zip file. Unzip the file to find the `EM__*.json` file.


Alternatively, the `EM__*.json` can be downloaded from the [Blue Brain Open Data](https://registry.opendata.aws/bluebrain_opendata/). We'll it to run the notebook. 


1. Install [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-welcome.html) based on [instructions](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) for your operating system if you are running locally on your PC.
1. Run the following command:
!aws s3 cp --no-sign-request s3://openbluebrain/Model_Data/Electrophysiological_models/SSCx/OBP_SSCx/emodels/detailed/cADpyr/EM__emodel=cADpyr__etype=cADpyr__mtype=L5_TPC_A__species=mouse__brain_region=grey__iteration=1372346__13.json ./

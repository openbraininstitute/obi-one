# Parameter comparison plots among section of an e-model 

Author: Darshan Mandge, Open Brain Institute

Copyright (c) 2025 Open Brain Institute

Last Modified: 06.2025

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
- The data downloading is done in the notebook. Simply follow the instructions there.

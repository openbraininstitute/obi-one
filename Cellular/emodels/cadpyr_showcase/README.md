# cADpyr e-model Showcase
Copyright (c) 2025 Open Brain Institute

Author: Darshan Mandge, Open Brain Institute

Last Modified: 02.2025

## Summary
The notebook showcases various properties of detailed morphology cADpyr (continuosly adapting type pyramidal neuron) e-model of the Open Brain Institute(OBI). 
It plots: 
- optimisation protocol responses
- [currentscape](https://github.com/openbraininstitute/Currentscape) analysis
- frequency-current (F-I) curve
- current-voltage (V-I) curve
- recordings in different sections of the neuron using [BlueCellulab](https://github.com/openbraininstitute/BlueCelluLab)
- dendritic potential decay 
- backpropagating action potential (bAP) recordings
- excitatory postsynaptic potential (EPSP) recordings and EPSP ratio.

## Use
Steps to run the notebook are given below:

1. The emodel data required to run this notebook (hoc file, morphology file, mechanisms and EModel resource json) can be downloaded from the [Blue Brain Open Data](https://registry.opendata.aws/bluebrain_opendata/). In future, you will be able to download the emodel data for different e-models directly from the Open Brain Platform.

1. Install [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-welcome.html) based on [instructions](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) for your operating system.

1. Run the following commands to donwload the data in folder `./cadpyr_emodel`:
    ```
    # check if the directory exists if not create it
    !if [ ! -d "cadpyr_emodel" ]; then mkdir cadpyr_emodel; fi 

    # download mechanisms (mod files)
    !aws s3 sync --no-sign-request s3://openbluebrain/Model_Data/Electrophysiological_models/SSCx/OBP_SSCx/emodels/detailed/cADpyr/mechanisms ./cadpyr_emodel/mechanisms 

    # hoc file
    !aws s3 cp --no-sign-request s3://openbluebrain/Model_Data/Electrophysiological_models/SSCx/OBP_SSCx/emodels/detailed/cADpyr/model.hoc ./cadpyr_emodel/model.hoc

    # morphology file 
    !aws s3 cp --no-sign-request s3://openbluebrain/Model_Data/Electrophysiological_models/SSCx/OBP_SSCx/emodels/detailed/cADpyr/C060114A5.asc ./cadpyr_emodel/C060114A5.asc

    # EModel json resource
    !aws s3 cp --no-sign-request s3://openbluebrain/Model_Data/Electrophysiological_models/SSCx/OBP_SSCx/emodels/detailed/cADpyr/EM__emodel=cADpyr__etype=cADpyr__mtype=L5_TPC_A__species=mouse__brain_region=grey__iteration=1372346__13.json ./cadpyr_emodel/
    ```

    You can also download the morphology from the platform:
    - Go to https://www.openbraininstitute.org/ `-->` Your virtual lab `-->` Explore `-->` Morphology (bottom of the page) `-->` in the searchbar, search for `C060114A5.asc` `-->` click on the morphology with species `Rattus norvegicus` `-->` Download (top of the page). 
        
    - This will download a zip file with morphology asc file. Extract the zip file and put the `C060114A5.asc` file in the `cadpyr_emodel` folder.

1. If you choose a different folder name, you need to update the  `emodel_folder_path` with relative path your folder name 
e.g.  `emodel_folder_path=Path("./your_folder_name")`

    The `emodel_name` (str, optional) can also be changed. Currently, it is set to `cadpyr_emodel`. The detailed instructions are also available in the notebook.

1. Now, you should be able to run the notebook. Follow the notebook text and comments in notebook to learn more about the e-model and results.

    You can also test this notebook other pyramidal neuron e-models of OBI. Follow the Step 1 above to replace the models files from OBI platform and update the `emodel_folder_path`.

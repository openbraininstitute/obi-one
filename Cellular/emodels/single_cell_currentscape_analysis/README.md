# Single cell currentscape analysis

Copyright (c) 2025 Open Brain Institute

Authors: Aurélien Jaquier, Open Brain Institute

Last modified: 02.2025

## Summary

This notebook showcases how to run a single cell with a step stimulus, record its mechanism-related currents and voltage output, and plot them as a currentscape graph, in the style of [Alonso and Marder (2019)](https://doi.org/10.7554/eLife.42722).

## Use

The software requirements of the notebook are mentioned in the `analysis_info.json`. Steps to run the notebook are given below:

### Donwloading Data
-  The emodel data required to run this notebook (hoc file, morphology file, mechanisms, EModel resource metadata json) can be downloaded from the [Blue Brain Open Data](https://registry.opendata.aws/bluebrain_opendata/). In future, you will be able to download the emodel data for different emodels directly from the Open Brain Platform.

    - If you are running the notebook locally on a PC, install [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-welcome.html) based on [instructions](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) for your operating system.
    - run the following commands:
    ```
    # check if the directory exists if not create it
    !if [ ! -d "cadpyr_emodel" ]; then mkdir cadpyr_emodel; fi 

    # download mechanisms (mod files)
    !aws s3 sync --no-sign-request s3://openbluebrain/Model_Data/Electrophysiological_models/SSCx/OBP_SSCx/emodels/detailed/cADpyr/mechanisms ./cadpyr_emodel/mechanisms 

    # hoc file
    !aws s3 cp --no-sign-request s3://openbluebrain/Model_Data/Electrophysiological_models/SSCx/OBP_SSCx/emodels/detailed/cADpyr/model.hoc ./cadpyr_emodel/model.hoc

    # morphology file 
    !aws s3 cp --no-sign-request s3://openbluebrain/Model_Data/Electrophysiological_models/SSCx/OBP_SSCx/emodels/detailed/cADpyr/C060114A5.asc ./cadpyr_emodel/C060114A5.asc

    EModel json
    !aws s3 cp --no-sign-request s3://openbluebrain/Model_Data/Electrophysiological_models/SSCx/OBP_SSCx/emodels/detailed/cADpyr/EM__emodel=cADpyr__etype=cADpyr__mtype=L5_TPC_A__species=mouse__brain_region=grey__iteration=1372346__13.json ./cadpyr_emodel/metadata.json
    ```

    The downloaded folder with data is `./cadpyr_emodel`.

    - You can also download the morphology from the platform:

        - Go to https://www.openbraininstitute.org/ `-->` Your virtual lab `-->` Explore `-->` Morphology (bottom of the page) `-->` in the searchbar, search for `C060114A5.asc` `-->` click on the morphology with species `Rattus norvegicus` `-->` Download (top of the page). 
        
            This will download a zip file with morphology asc file. Extract the zip file and put the `C060114A5.asc` file in the `cadpyr_emodel` folder.

- Follow the instructions within the notebook to learn more about the model and results.

## Publication

The currentscape style plots have been introduced by [Alonso and Marder (2019)](https://doi.org/10.7554/eLife.42722).

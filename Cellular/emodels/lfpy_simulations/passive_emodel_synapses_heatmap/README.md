# LFPy: passive e-model with synapse -- plot LFP Heatmap

Author: Darshan Mandge, Open Brain Institute

Copyright (c) 2025 Open Brain Institute

Last Modified: 02.2025

## Summary
Notebook to apply synapses and using LFPy, recording local field potentials and plotting heatmap

## Use

-  The emodel data required to run this notebook (hoc file, morphology file and mechanisms) can be downloaded from the [Blue Brain Open Data](https://registry.opendata.aws/bluebrain_opendata/). In future, you will be able to download the emodel data for different emodels directly from the Open Brain Platform.

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
    ```

    The downloaded folder with data is `./cadpyr_emodel`.

    - You can also download the morphology from the platform:

        - Go to https://www.openbraininstitute.org/ `-->` Your virtual lab `-->` Explore `-->` Morphology (bottom of the page) `-->` in the searchbar, search for `C060114A5.asc` `-->` click on the morphology with species `Rattus norvegicus` `-->` Download (top of the page). 
        
            This will download a zip file with morphology asc file. Extract the zip file and put the `C060114A5.asc` file in the `cadpyr_emodel` folder.

- Follow the instructions within the notebook to generate the results.

- The notebook shows the extracellular response of a synaptic input to a passive cADpyr neuron. To use it for a different model replace the morphology in the CellParameters dictionary.
# "Current clamp efeature extraction

Author: Darshan Mandge, Open Brain Institute

Copyright (c) 2025 Open Brain Institute

Last modified: 02.2025


## Summary
This notebook demonstrates how to load electrophysiology data using h5py for eFEL e-features extraction.

## Use
To run the notebook, you will need a current clamp experiment NWB file. After getting the data follow the instructions in the notebook.

We will use the recordings obtained from the recording file C291001A2-MT-C1.nwb. The traces come electrophysiological patch clamp slice recordings of a bSTUT eleectrical firing type (e-type) cell of rat isocortex. The file can be obtained by visiting the Electrophysiology Data page of the portal.

We'll obtain this file from the [Blue Brain Open Data](https://registry.opendata.aws/bluebrain_opendata/). 

### Get the data
- Install [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-welcome.html) based on [instructions](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) for your operating system if you are running locally on your PC.
- Run the following commands:

    `!aws s3 cp --no-sign-request s3://openbluebrain/Experimental_Data/Electrophysiological_recordings/Single-cell_recordings/Rat/SSCx/C291001A2-MT-C1.nwb ./`


## Notes
- Here we show how to use [eFEL](https://github.com/openbraininstitute/eFEL) extract e-features from the whole cell patch clamp electrophysiology data. 
- The data is in nwb format.
- Users can use various [electrical features](https://efel.readthedocs.io/en/latest/eFeatures.html)
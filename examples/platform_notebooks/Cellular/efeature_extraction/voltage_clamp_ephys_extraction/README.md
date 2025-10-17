# Voltage clamp efeature extraction

Author: Darshan Mandge, Open Brain Institute

Copyright (c) 2025 Open Brain Institute

Last modified: 02.2025


## Summary
This notebook demonstrates how to load electrophysiology data using h5py for eFEL e-features extraction. We will use a NWB data voltage clamp experiments on cells expressing an ion channel gene.

The NWB data file contains experimental data from patch clamp experiments as described in [Ranjan et al. 2019](https://doi.org/10.3389/fncel.2019.00358). 

The experiments were performed on cells from cell lines such as Chinese hamster ovary (CHO). The CHO cells do not have their own native channel expressed. Individual ion channel genes cloned from rat/mouse are expressed in these cells and automated patch clamp recordings are performed on these cells. 

The [data](https://channelpedia.epfl.ch/expdata/details/9430) is from Cell line: CHO FT rKv1.1. The gene expressed is for Kv1.1 ion channel cloned from rat cells. The recordings were made at 25 degree celsius.

The patched cells were held at different voltage clamp levels and the intracellular currents were recorded for activation, inactivation and deactivation properties of the ion channels.

The goal of this notebook is to extract features for these properties which are then useful to construct ion channels.

## Use

This notebook explains how to use traces from voltage clamp in eFEL. First, you need to load your modules and your trace data. Here, we will use experimental data from Channelpedia: https://channelpedia.epfl.ch/expdata/details/9430

    Ranjan R, Logette E, Marani M, Herzog M, Tache V, Scantamburlo E, Buchillier V and Markram H (2019) A Kinetic Map of the Homomeric Voltage-Gated Potassium Channel (Kv) Family. Front. Cell. Neurosci. 13:358. https://doi.org/10.3389/fncel.2019.00358


### Get the data
In future, the data used for the notebook will be available through the Open Brain Platform. For now, you can obtain the data by two ways:

1. **Channelpedia**: 
You will need to [create an account](https://channelpedia.epfl.ch/register) in [Channelpedia](https://channelpedia.epfl.ch) download nwb file from this [page](https://channelpedia.epfl.ch/expdata/details/9430).
2. **Blue Brain Open Data**
You can obtain the nwb file from the [Blue Brain Open Data](https://registry.opendata.aws/bluebrain_opendata/) using AWS CLI. We will follow this approach in this notebook. Below are the steps to get the file from Open Data:

    - Install [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-welcome.html) based on [instructions](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) for your operating system if you are running locally on your PC.
    - Run the following command:

        `!aws s3 cp --no-sign-request s3://openbluebrain/Experimental_Data/Electrophysiological_recordings/Ion_channels/Kv/Kv1.1/rCell9430.nwb ./`


## Notes
- Here we show how to use [eFEL](https://github.com/openbraininstitute/eFEL) extract e-features from current traces recorded from voltage experimentes
- The data is in nwb format.
- Users can use various [electrical features](https://efel.readthedocs.io/en/latest/eFeatures.html)
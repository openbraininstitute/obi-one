# Voltage clamp efeature extraction

Author: Darshan Mandge, Open Brain Institute

Copyright (c) 2025 Open Brain Institute

Last modified: 02.2025


## Summary
This notebook demonstrates how to load electrophysiology data using h5py for eFEL e-features extraction.

## Use

This notebook explains how to use traces from voltage clamp in eFEL. First, you need voltage clamp data. Here, we will use experimental data from Channelpedia: https://channelpedia.epfl.ch/expdata/details/9430

Ranjan R, Logette E, Marani M, Herzog M, Tache V, Scantamburlo E, Buchillier V and Markram H (2019) A Kinetic Map of the Homomeric Voltage-Gated Potassium Channel (Kv) Family. Front. Cell. Neurosci. 13:358. doi: 10.3389/fncel.2019.00358

Blue Brain Project Portal (https://portal.bluebrain.epfl.ch) and Channelpedia (https://channelpedia.epfl.ch)

You will need to create an account in channelpedia tp download the file. In future, the data will be available through the Open Brain Platform. 

After, you have the data, follow the instructions in the notebook to extract features from ion channel voltage clamp recordings.



## Notes
- Here we show how to use [eFEL](https://github.com/openbraininstitute/eFEL) extract e-features from current traces recorded from voltage experimentes
- The data is in nwb format.
- Users can use various [electrical features](https://efel.readthedocs.io/en/latest/eFeatures.html)
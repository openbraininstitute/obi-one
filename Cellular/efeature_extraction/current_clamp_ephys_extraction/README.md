# "Current clamp efeature extraction

Author: Darshan Mandge, Open Brain Institute

Copyright (c) 2025 Open Brain Institute

Last modified: 02.2025


## Summary
This notebook demonstrates how to load electrophysiology data using h5py for eFEL e-features extraction.

## Use
Follow the instructions in notebook. You will need a current clamp experiment NWB file. 
A sample nwb is present [here](https://openbraininstitute.sharepoint.com/:u:/s/OBI-Scientificstaff/Eb8FqyQL2rdGnhd4kMu1MyoBdG8HtnAkDCL_Mfx4Y1H7gQ?e=UWZWSh) in OneDrive location: `OBI -> Scientific staff -> Documents -> Data -> Analysis notebook data -> ephys`. 

Download the folder with the file and put it here `./Cellular/efeature_extraction`

## Notes
- Here we show how to use [eFEL](https://github.com/openbraininstitute/eFEL) extract e-features from the whole cell patch clamp electrophysiology data. 
- The data is in nwb format.
- Users can use various [electrical features](https://efel.readthedocs.io/en/latest/eFeatures.html)
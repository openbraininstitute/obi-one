# Voltage clamp efeature extraction

Author: Darshan Mandge, Open Brain Institute

Copyright (c) 2025 Open Brain Institute

Last modified: 02.2025


## Summary
This notebook demonstrates how to load electrophysiology data using h5py for eFEL e-features extraction.

## Use
Follow the instructions in the notebook. You will first need to download a voltage clamp experiment NWB.
A smaple file is present in [here](https://openbraininstitute.sharepoint.com/:u:/s/OBI-Scientificstaff/EWpiWrth3gJMu1uVox1OrRMB0DByhMOzqKeeShvS01A7AA?e=O6qt9k) in OneDrive location: ``OBI -> Scientific staff -> Documents -> Data -> Analysis notebook data -> ephys`

Download the folder with the file and put it here `./Cellular/efeature_extraction`

## Notes
- Here we show how to use [eFEL](https://github.com/openbraininstitute/eFEL) extract e-features from current traces recorded from voltage experimentes
- The data is in nwb format.
- Users can use various [electrical features](https://efel.readthedocs.io/en/latest/eFeatures.html)
# Single cell currentscape analysis

Copyright (c) 2025 Open Brain Institute

Authors: Aurélien Jaquier, Open Brain Institute

Last modified: 02.2025

## Summary

This notebook showcases how to run a single cell with a step stimulus, record its mechanism-related currents and voltage output, and plot them as a currentscape graph, in the style of [Alonso and Marder (2019)](https://doi.org/10.7554/eLife.42722).

## Use

The software requirements of the notebook are mentioned in the `analysis_info.json`. Steps to run the notebook are given below:
1. An `emodel.zip` file containing the e-model model `hoc` file,  `.asc` morphology file, mechanism folder containing mechanisms (`.mod`) files and a metadata `.json` file should be obtained from OBI. These could be downloaded from (temporary for testing purpose) [here](https://openbraininstitute.sharepoint.com/:f:/s/OBI-Scientificstaff/EpqQOMfkUoRIv5mkPmaTdWEBuVeg6qEi93fJbmy-FSsgRA?e=SwGY4V) in a private folder.
2. Place the `emodel.zip` file in your current working directory.
3. Now, you should be able to run the notebook. Follow the text and comments in notebook to learn more about the model and results.

## Publication

The currentscape style plots have been introduced by [Alonso and Marder (2019)](https://doi.org/10.7554/eLife.42722).

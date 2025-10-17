# Morphology quality check
Copyright (c) 2025 Open Brain Institute

Authors: Michael W. Reimann

last modified: 08.2025

## Summary
This analysis tests a list of morphologies against some common issues that may cause issues with tools and analyses using the morphologies.

## Use
Simply run the cells of the notebook. 

When running the first cell, you will be prompted to follow a link to set up authentication with the platform.

In the third cell you will have to fill in the IDs of the morphologies you wish to analyze. You can copy them from the "explore" functionality of the platform and paste them here.
We acknowledge that this is a very roundabout way of doing this and apologize. We are working on implementing a better approach!

Continue running cells until the dropdown menu is depicted. It displays the types of morphology files found (i.e., by their extension). Select the types you want to analyze.


Continue running until the plot is displayed. The green bars depict the number of morphologies that passed a given test. The red bars stacked on top depicts the number that failed. If the number that passed plus the number that failed is lower than the number of morphologies loaded, it indicates that a test failed to run to completion.


From the dropdown menu select the name of a test. The names of the morphologies that failed the test will be displayed. All tests are implemented in the [NeuroM](https://github.com/BlueBrain/NeuroM) library. Please refer to the [documentation of this library](https://neurom.readthedocs.io/en/stable/features.html) for specifics.

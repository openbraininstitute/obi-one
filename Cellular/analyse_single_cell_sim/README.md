# Display single cell simulation results
Copyright (c) 2025 Open Brain Institute

Authors: Michael W. Reimann

last modified: 02.2025

## Summary
Plots: (1) Recorded voltage traces from the output of single cell simulations. (2) Spike counts detected in the output of single cell simulations. To be used as a starting point for more complex analyses.

## Use
Simply run the cells of the notebook. 

In the first plotting cell, three choices have to be made: First, select the number of the _simulation run_ to be plotted. Often, only a single run is contained in a file, so the default value of 0 can be left unchanged. Next, the resulting traces are associated with a number of properties that depend on the specifics of the simulation campaign. This can be an indicator of the recording locations or properties of the stimulus applied. Select one such property in the first dropdown and a value of that property in the second dropdown and all traces that match the property / value pair will be plotted.

In the second plotting cell, once again the number of the _simulation run_ is first selected. Then, two properties are to be selected. Values of the first will determine the order of the results along the x-axis, the second one the order along the y-axis. The number of spikes detected by a primitive spike detector is then indicated by the color and sizes of markers at the x- and y-locations determined this way.

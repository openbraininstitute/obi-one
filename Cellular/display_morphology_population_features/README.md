# Display morphology population features
## Summary
This analysis extracts morphology features from a list of morphologies and displays the distribution of their values as a histogram.

## Use
Simply run the cells of the notebook until the first dropdown menu is displayed. In this menu, select the feature to display. The list contains all morphology and neurite features in the [NeuroM](https://github.com/BlueBrain/NeuroM) library. Please refer to the [documentation of this library](https://neurom.readthedocs.io/en/stable/features.html) for specifics.

In the next dropdown menu, select by which parameter (such as neurite type, morphological type, etc.) the plot should be grouped. Data will be plotted separately as stacked bar plots for different values of that parameter. The slider determines the number of bins.

After the plot has been generated, you can select different values from the dropdown menus and the slider and re-run the cells to update the plot accordingly.
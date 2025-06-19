# Circuit composition
Copyright (c) 2025 Open Brain Institute

Authors: Michael W. Reimann

last modified: 01.2025

## Summary
This analysis displays the composition of a circuit model with respect to user-selected neuron properties, such as morphological types, electrical types, home layers, etc. It is displayed as a Sankey plot, allowing the user to see, e.g., how many neurons of a given morphological type have a given electrical type.

## Use
Simply run the cells of the notebook until the first dropdown menu is displayed. In this menu, select the *node set* to display the composition of. A node set is a conceptual group of neurons in the model, such as all inhibitory cells. For details see [this documentation](https://sonata-extension.readthedocs.io/en/latest/sonata_nodeset.html).

Next, a list of available properties is displayed. The number and types of properties depends on the circuit model. Only *categorical* properties are displayed. Select between two and eight of the properties from the list. You may have to shift-click on the elements to select or de-select multiples.

Finally, after executing the last cell, the Sanker plot is displayed.

After the plot has been generated, you can select different values from the dropdown menus and the selector and re-run the cells to update the plot accordingly.
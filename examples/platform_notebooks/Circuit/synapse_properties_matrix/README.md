# Extract and display a synapse property matrix from a SONATA circuit
Copyright (c) 2025 Open Brain Institute

Authors: Christoph Pokorny

Last modified: 08.2025

## Summary
This analysis extracts and visualizes a matrix of a selected synapse property (conductance, delay, ...), grouped by a selected neuron property (layer, m-type, ...).

## Use
After loading a [SONATA](https://github.com/AllenInstitute/sonata/blob/master/docs/SONATA_DEVELOPER_GUIDE.md) circuit, the user can select one [_edge population_](https://github.com/AllenInstitute/sonata/blob/master/docs/SONATA_DEVELOPER_GUIDE.md#representing-edges) (containing connections, formed by synapses) to extract the connectivity from. In general, a SONATA circuit may contain more than one edge population in which case only one can be used at a time.

As a next step, the user can optionally select a pre- and post-synaptic _node set_ which is a conceptual group of neurons defined in the circuit's [_node sets file_](https://github.com/AllenInstitute/sonata/blob/master/docs/SONATA_DEVELOPER_GUIDE.md#node-sets-file). 

Finally, the user can select a neuron property (e.g., layer, m-type, etc.) based on which to group the pre- and post-synaptic neurons, and the respective properties matrix between all pairs of groups will be extracted. Optionally, the user can choose which grouping function to use for computing a matrix entry from a group of values (default: mean). For visualization, the (physiological) synapse property of interest, and whether or not to display empty groups (i.e., groups w/o any neurons or connections), can be selected interactively.
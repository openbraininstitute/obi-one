# Extract and display an adjacency matrix from a SONATA circuit
Copyright (c) 2025 Open Brain Institute

Authors: Christoph Pokorny

Last modified: 08.2025

## Summary
This analysis extracts and visualizes the connectivity between all pairs of pre- and post-synaptic neurons (adjacency matrix), optionally including the number of synapses per connection (synaptome matrix).

## Use
After loading a [SONATA](https://github.com/AllenInstitute/sonata/blob/master/docs/SONATA_DEVELOPER_GUIDE.md) circuit, the user can select one [_edge population_](https://github.com/AllenInstitute/sonata/blob/master/docs/SONATA_DEVELOPER_GUIDE.md#representing-edges) (containing connections, formed by synapses) to extract the adjacency matrix from. In general, a SONATA circuit may contain more than one edge population in which case only one can be used at a time.

As a next step, the user can optionally select a pre- and post-synaptic _node set_ which is a conceptual group of neurons defined in the circuit's [_node sets file_](https://github.com/AllenInstitute/sonata/blob/master/docs/SONATA_DEVELOPER_GUIDE.md#node-sets-file). 

Finally, the respective adjacency and synaptome matrices will be extracted and visualized. The user can select which one to display, and can manually adjust the marker scaling and transparency for optimal display depending on the actual matrix and screen size.
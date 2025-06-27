# Compare proximal and distal inhibition
Copyright (c) 2025 Open Brain Institute

Authors: Michael W. Reimann

last modified: 06.2025

## Summary
We distinguish proximal vs. distal innervation on a dendrite by the path distance of a synapse to the post-synaptic soma. This uses an arbitray cutoff, such as 100 um. 

In this notebook, we compare the effect of proximal vs. distal inhibition on spike counts of a neuron receiving excitatory inputs. 
It takes the results of three single neurons synaptome simulatons as inputs:
1. One where only the excitatory synaptic inputs of the neuron were activated with various frequencies
2. One where the excitatory inputs were activated at a given frequency, and concurrently the _proximal_ inhibitory inputs were activated at various frequencies
3. One as #2 above, but for the _distal_ instead of the proximal inhibitory inputs.

It then creates two plots: One of excitatory input frequency vs. output spike count, and one of inhibitory input frequencies vs. output spike counts.

## Use
In the first cell, fill in the following:
1. The id of the simulation with excitatory inputs only as "exc-only".
2. The id of the simulation combining excitatory inputs with proximal inhibition as "inh-prox".
3. The id of the simulation combining excitatory inputs with distal inhibition as "inh-dist".
4. The excitatory input frequency used for the simulations combining excitatory inputs with inhibitory inputs as "freq_e_used"

Then, simply run the cells of the notebook. 

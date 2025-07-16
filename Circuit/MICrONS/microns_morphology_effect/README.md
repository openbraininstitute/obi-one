# MICrONS morphology connectivity effect
Copyright (c) 2025 Open Brain Institute

Authors: Michael W. Reimann

Last modified: 06.2025

## Summary
We will perform a proof-of-concept analysis that reveals how structured and non-random the connectivity is. Specifically, we will test the following hypothesis.

It has been demonstrated before, that modeled networks based on axo-dendritic touch generate a highly non-random structure that matches biological characteristics better than simpler, connection probability-based models. Such characteristics are for example degree distributions, and motif overexpression patterns.

We formulate a hypothesis of what mechanism leads to this and test it using the MICrONS data. The hypothesis is as follows:

  1. A required (although not sufficient) condition for the formation of a connection is proximity of the axon to the dendrite
  2. This condition can in principle be formulated as a distance and direction-dependent probability function on the offset between somata of a neuron pair. 
  3. The shape of this function is determined by the overall average shape of the dendrites and axons of the classes of neurons considered.
  4. However, once a connection at a given distance and direction has been confirmed for a given pre-/post-synaptic neuron, this function must be updated for all its future potential connections. This is because presence of the connection demonstrates that the axon / dendrites are more likely to be oriented towards the point where the connection has been formed.
  5. On a theoretical level, this introduces a _statistical dependence_ between connections: Presence or absence of one connection influences the probability that another connection is present. This is something that connection probability-dependent models, even complex ones, cannot capture, as they are based on statistically independent evaluations of connection probabilities.

We consider points 1-3 to be widely accepted. Points 4 and 5 describe aplausible scenario. But we have to demonstrate that the proposed mechanism actually affects connectivity on a measurable level. To do so, we test a prediction derived from the hypothesis.

**Prediction**: If a neuron A innervates / is innervated by a neuron B, then the probability that it also innervates / is innervated by the _nearest spatial neighbor_ of B is increased.

## Use
Simply follow the instructions set out in the notebook.

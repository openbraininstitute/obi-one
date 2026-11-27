---
tags:
  - circuit-simulation
---

# Circuit Simulation Resources

The nodes allocated to a neurodamus circuit simulation come from the memory it needs, and that memory comes mostly from the synapses onto the simulated cells, not from the cells. An SSCX cell has about 2,400 synapses, and an rCA1 cell about 22,000, 92% of them from the CA3 projection. A rule per cell that fits one does not fit the other (openbraininstitute/prod-circuit-simulation#265).

## Counting the synapses at generation

Generation records three counts on the `Simulation` next to `number_neurons`:

- `number_synapses`: the synapses of the chemical edge populations onto the biophysical cells of the node set, as neurodamus creates them.
- `number_replayed_synapses`: those whose source spikes in a spike stimulus. For each source population, its synapses times the share of its nodes that spike, times 2.5 for source sets that project more than the mean onto the simulated cells, up to all of them. The spike files are those generation writes, read in chunks.
- `number_replay_spikes`: the spikes of all the spike files.

Each count is recorded only if the installed entitysdk's `Simulation` has the field.

Generation runs in the API service with the nodes of the circuit staged and not its edges, which can be many GB. The synapses come from the `indices/target_to_source` index of each edges file: `node_id_to_ranges` gives each cell its ranges of `range_to_edge_id`, which give its edges. The index is read with `Client.open_file`, from the local asset store when it has the file and otherwise with HTTP range reads, 256 KB at a time. The synapses per cell of a circuit are kept in the memory of the service (4 bytes per cell, at most 16 circuits), so only the first simulation of a circuit reads them.

The layout of an edge population is not trusted. Its synapses are counted per cell only if its index is no larger than 32 MB (a population of 1M cells) and accounts for every one of its edges. Otherwise it is counted in total, from the shape of `source_node_id` (HDF5 metadata), and a node set gets its share of the cells times 2.5, capped at the total. The 2.5 covers the node sets that hold more synapses per cell than the mean: the cells of one layer hold up to 2.2 times the mean in the SSCX circuits. Rows of an index beyond the population are ignored. An edges file that cannot be read, or any other error, records the neuron count only.

The edge files of all the circuits of staging and production (2,926 on 2026-11-26) are sorted by target and indexed. What the rules above catch:

- The `target_to_source` index of some synaptome circuits leaves out the last cell, and the edges onto it (Multi-synaptome). That population is counted in total.
- The index of others has more rows than the population, all empty (Afferent-synaptome). The extra rows are ignored.
- The indices of nbS1 (4.2M cells) are 68 MB per edge population. Its populations are counted in total.

## Memory and nodes

`app/services/resource_estimation/circuit_simulation.py` gives a simulation the nodes that hold its peak memory. The model was fitted on 76 runs in the simulation image (neurodamus 4.2.11 and 4.3.0, NEURON and CoreNEURON, rCA1 and SSCX cells, 1 to 16 ranks, with and without replay, reports and LFP), and the measurements, the fit and its checks are in [Circuit Simulation Memory Measurements](circuit-simulation-memory-measurements.md).

Held by every MPI rank, so paid on every node whatever their number (launch-system runs one rank per core, `ranks_per_instance`):

- 34.9 MB per rank.
- 41.4 bytes per replay spike per rank: every rank reads all the spike files while it sets up the replay.
- 6.5 MB per rank with LFP.

Split over the nodes:

- 5.55 MB per cell.
- 3.07 KB per synapse. neurodamus creates every synapse, replayed or not.
- 2.05 KB per replayed synapse, for the spike train and NetCon of its connection.
- 1.04 times the LFP weights of the simulated cells. The weight matrix of a recording array covers its whole circuit, so it counts for the simulated share of the circuit's cells, times 2.5, up to all of it.

Both are times 1.15: the largest measured peak was 1.09 times the fit, and the CA1 job `01a1cb34` ran out of memory on one node at about 1.06 times it (about 4 GB on each of 192 ranks, against 722 GB from the fit). A node gives the simulation 90% of its memory. The nodes are the split memory over what a node has left after its own share, and at least 0.03 GB per cell, the rule SSCX simulations have run with.

- The CA1 job (9,587 cells, 219.1M synapses, 5.4% of the CA3 sources replayed) gets 2 nodes of cell_a: it ran out of memory on one node and ran on two.
- The same with every CA3 source spiking at 10 Hz for 5 s (13.4M spikes) gets 3: the spikes take about 100 GB of every node before the margin, 114 GB with it.
- Spike inputs that no node can hold make the estimate fail with an error that says so, since more nodes would not help.
- A simulation that needs more nodes than an instance type offers (`max_instances`: 20 large and 12 small nodes on cell_a, from `launch_system/pcs.tf` in aws-terraform-deployment) fails the same way, instead of waiting in the queue. On cell_a that is the whole rCA1 circuit (456k cells, 54 nodes); its node sets fit up to about 170k cells without replay, 110k with every CA3 source replayed.
- SSCX circuits get the 0.03 GB per cell floor, as before.
- A simulation without a synapse count (`number_synapses` absent or 0, as for those generated before it existed) keeps 0.09 GB per cell.

What the model does not cover: recordings (their buffers are a few MB per rank and were within the noise of the runs), runs much longer than 3 s (a 3 s run used 4% more than a 100 ms one), and circuits whose cells were not measured, which the floor covers.

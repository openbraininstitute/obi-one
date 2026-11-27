---
tags:
  - circuit-simulation
---

# Circuit Simulation Resources

The nodes allocated to a neurodamus circuit simulation come from the memory it needs, and that memory comes mostly from the synapses onto the simulated cells, from their replay and from the replay spike files, not from the cells. An SSCX cell has about 2,400 synapses, and an rCA1 cell about 22,000, 92% of them from the CA3 projection. A rule per cell that fits one does not fit the other (openbraininstitute/prod-circuit-simulation#265). The measurements behind the constants below are in [Circuit Simulation Memory Measurements](circuit-simulation-memory-measurements.md).

## Counting at generation

Generation (`GenerateSimulationTask`, through `simulation_synapse_counts` of `obi_one/scientific/library/simulation_synapses.py`) records three counts on the `Simulation` next to `number_neurons`, each only if the installed entitysdk's `Simulation` has the field:

- `number_synapses`: the synapses of the chemical edge populations onto the biophysical cells of the node set, as neurodamus creates them (`obi_one/scientific/library/circuit_synapses.py`).
- `number_replayed_synapses`: those whose source spikes in a spike stimulus. For each source population, its synapses times the share of its nodes that spike, times `SUBSET_FACTOR`, up to all of them (`obi_one/scientific/library/replay_inputs.py`).
- `number_replay_spikes`: the spikes of all the spike files generation wrote.

Any error while counting records the neuron count only.

Generation runs in the API service with the nodes of the circuit staged and not its edges, which can be many GB. The synapses come from the `indices/target_to_source` index of each edges file: `node_id_to_ranges` gives each cell its ranges of `range_to_edge_id`, which give its edges. The index is read with `Client.open_file`, from the local asset store if it has the file and otherwise with HTTP range reads of `REMOTE_BLOCK_SIZE`. The simulations of a campaign share the staged circuit, so the first one reads the synapses per cell and writes them next to the staged circuit config (`SYNAPSES_FILE_NAME`), and the others load that file. Nothing is kept in the service between requests: each campaign reads the indices once.

The layout of an edges file is not trusted. An edge population is counted per cell only if its index is at most `MAX_INDEX_BYTES` and accounts for every one of its edges. Otherwise it is counted in total from the shape of `source_node_id` (HDF5 metadata), and a node set gets its share of the cells times `SUBSET_FACTOR`, up to the total. Rows of an index beyond the population are ignored. What this catches in the circuits of staging and production (2,926 on 2026-11-26):

- The `target_to_source` index of the Multi-synaptome circuits leaves out the last cell and the edges onto it. That population is counted in total.
- The index of the Afferent-synaptome circuits has more rows than the population, all empty. The extra rows are ignored.
- nbS1 and nbS1-midrange (4.2M cells) have 68 MB of index per edge population, counted in total.

## Memory and nodes

`app/services/resource_estimation/circuit_simulation.py`, with `R` the ranks of a node (`ranks_per_instance`), `M` its memory (`memory_per_instance_gb`), and the counts of the `Simulation`:

```
per_node = peak_memory_safety_factor * R * (gb_per_rank + gb_per_replay_spike_per_rank * spikes + gb_per_rank_with_lfp if LFP)
split    = peak_memory_safety_factor * (gb_per_cell * cells + gb_per_synapse * synapses
                                        + gb_per_replayed_synapse * replayed + lfp_weights_factor * LFP weights)
nodes    = max(ceil(split / ((1 - reserved_node_memory_fraction) * M - per_node)), ceil(min_gb_per_cell * cells / M))
```

The terms are the fields of the frozen pydantic model `MemoryModel`, whose defaults are the values below; `MEMORY_MODEL` is the instance the estimator uses, and its methods `per_node_gb` and `split_gb` compute the two parts.

`per_node` is paid on every node whatever their number, since every rank holds it. The LFP weights are those of the simulated cells: the weight matrix of each recording array covers its whole circuit (generation refuses arrays of another circuit), so it counts for the simulated share of the circuit's cells, times `SUBSET_FACTOR`, up to all of it.

The estimate is refused, with an error that says why, if `per_node` is more than the usable memory of a node (spike inputs every rank must hold, whatever the number of nodes), or if the nodes are more than `max_instances`. A simulation without a synapse count (`number_synapses` 0, as for those generated before it existed) gets `uncounted_gb_per_cell` per cell.

## Constants

### Memory model (`MemoryModel` in `app/services/resource_estimation/circuit_simulation.py`)

The terms were fitted with non-negative least squares on relative errors over 76 runs in the simulation image: neurodamus 4.2.11 and 4.3.0, NEURON and CoreNEURON, rCA1 and SSCX cells, 1 to 16 ranks, with and without replay, spike files, reports and LFP. Memory is the anonymous and shared memory of the job's cgroup at its peak, what the OOM killer counts.

| Field | Value | Represents | How it was obtained |
|---|---|---|---|
| `gb_per_rank` | 34.9 MB | An MPI rank: NEURON, neurodamus, Python and MPI, before any cell. | Fit; 1 to 16 ranks on the same 48 rCA1 cells. |
| `gb_per_replay_spike_per_rank` | 41.4 B | A spike of the replay files, on every rank: each reads all the files whole while it sets the replay up, about 2.6 copies of the 16 bytes of a spike. | Not fitted: the exact peak (`VmHWM`) of a rank, 16 ranks, 13.4M spikes against 267k. With fewer ranks a rank's share of the model hides this transient. |
| `gb_per_rank_with_lfp` | 6.5 MB | What a rank adds with an LFP report, whatever the electrodes. | Fit; LFP with 16 to 1,024 electrodes on 48 and 128 rCA1 and 400 SSCX cells, neurodamus 4.3.0. |
| `gb_per_cell` | 5.55 MB | A cell without its synapses: sections, mechanisms, its share of the model. | Fit; separated from the synapses by SSCX (2.4k synapses per cell) against rCA1 (19k). |
| `gb_per_synapse` | 3.07 KB | A synapse, loaded and instantiated. neurodamus 4.2.11 and 4.3.0 create every synapse, replayed or not. | Fit; 288k to 4.9M synapses. |
| `gb_per_replayed_synapse` | 2.05 KB | The spike train (`VecStim`) and `NetCon` of a replayed connection, counted per replayed synapse: a connection has one synapse or more (1.1 in the CA3 projection), so this errs on the safe side. | Fit; 0 to 100% of the CA3 (and VPM, POm) sources replayed. |
| `lfp_weights_factor` | 1.04 | The LFP weights of the simulated cells (segments × electrodes × 8 bytes), as neurodamus copies them for CoreNEURON. | Fit; summed and per-cell LFP cost the same. |
| `peak_memory_safety_factor` | 1.15 | The factor on the fitted peak memory. | The largest measured peak was 1.09 times the fit, runs repeated in different sessions differ by 2 to 4%, and the CA1 job `01a1cb34` ran out of memory on one node at about 1.06 times the fit (about 4 GB on each of 192 ranks, against 722 GB). |
| `reserved_node_memory_fraction` | 0.1 | The share of a node's memory kept for the system, the 750 MB Slurm reserves on cell_a (`MemSpecLimit`) and MPI; the simulation gets the rest. | Chosen, not measured. |
| `min_gb_per_cell` | 0.03 GB | A floor: the rule SSCX simulations ran with. | The lowest memory per cell of production runs was about 0.025 GB ([sheet](https://openbraininstitute.sharepoint.com/:x:/s/OpenBrainInstitute/IQBgZ53Oe1GhQZQOjc6b_NqlAfobEWCRSznthvhc3X4CHZA?e=ayfe1a)), with some margin. The image measured SSCX at 0.013 to 0.016 GB per cell, a gap not explained, and circuits other than rCA1 and SSCX were not measured. |
| `uncounted_gb_per_cell` | 0.09 GB | The rule for simulations without a synapse count. | The 0.03 rule tripled for the CA3 projections of rCA1. |

### Counting (`obi_one/scientific/library/`)

| Constant | Value | Represents | How it was obtained |
|---|---|---|---|
| `MAX_INDEX_BYTES` (`circuit_synapses.py`) | 32 MB | The most index read per edge population, its node and range datasets, 16 bytes a row: a population of 1M cells sorted by target. Above it the population is counted in total. | Chosen so the service reads at most a few tens of MB. The largest indices read exactly are those of rCA1 (456k cells, 14.6 MB per population). |
| `SUBSET_FACTOR` (`circuit_synapses.py`) | 2.5 | How many times the mean share a node set, or a set of replayed sources, may hold of what is counted in total. | The uniform share against the exact counts of 371 populations: the cells of one layer or m-type (contiguous 10% blocks of node ids) hold up to 2.2 times the mean in SSCX, random 1% samples up to 2 times. |
| `SYNAPSES_FILE_NAME` (`circuit_synapses.py`) | `synapses_per_cell.npz` | The synapses per cell of a staged circuit, by population and source, as `read_synapses_per_cell` gives them: a `uint32` per cell and source counted exactly, a total per source counted in total. | 5.2 MB for the whole rCA1 circuit (456k cells, 3 sources), saved in 11 ms and loaded in 9 ms; populations counted in total store one number. |
| `REMOTE_BLOCK_SIZE` (`obi_one/db_sdk/circuit.py`) | 256 KB | Bytes per range request of a remote file. | An index is about 100 kB and a request takes the same time whatever its size: 4.5 to 5.4 s for the rCA1 slice against 6.3 to 8.6 s with 4 MB blocks; smaller gave nothing more. |
| `CHUNK` (`replay_inputs.py`) | 1M | Node ids read at once from a spike file, 8 bytes each. | Bounds the memory of the count: 13.4M spikes take 0.09 s and 23 MB. |

### Instances (`app/mappings.py`, `CLUSTER_INSTANCES_INFO`)

`ranks_per_instance` is the cores of a node: launch-system starts one rank per core (`nproc --all` × nodes). `max_instances` is the most nodes of the type a job can get; `None` if not known. A request for more would wait in the queue forever.

| Cell | Instance | Machine | `memory_per_instance_gb` | `ranks_per_instance` | `max_instances` | Source |
|---|---|---|---|---|---|---|
| cell_a | small | `t3a.xlarge`, 4 vCPU, 16 GiB | 16 | 4 (hardware threads) | 12 | aws-terraform-deployment `launch_system/pcs.tf` |
| cell_a | large | `hpc7a.96xlarge`, 192 cores, 768 GiB | 768 | 192 | 20 | `pcs_large_nodes_max_instance_count` in aws-terraform-deployment `main.tf`; no fallback instance type |
| cell_b | small | `Standard_D4s_v5`, 4 vCPU, 16 GiB | 8 | 4 | `None` | azure-terraform-deployment `batch/batch.tf` |
| cell_b | large | `Standard_HB176rs_v4`, 176 cores | 788 | 176 | `None` | azure-terraform-deployment `batch/batch.tf` |

The Azure pools autoscale with the active tasks and allocate their VMs in the subscription (`UserSubscription`), so their nodes are limited by its vCPU quota, which is not in the repository. launch-system sends cell_b jobs to the pools `largenode` and `timestamped-neurodamus`, which are not defined there either.

## What it gives

- The CA1 job (9,587 cells, 219.1M synapses, 5.4% of the CA3 sources replayed) gets 2 nodes of cell_a: it ran out of memory on one node and ran on two.
- The same with every CA3 source spiking at 10 Hz for 5 s (13.4M spikes) gets 3: the spikes take about 100 GB of every node before the margin, 114 GB with it.
- SSCX circuits get the `min_gb_per_cell` floor, as before. Of 122 circuits of staging and production simulated whole, 112 get the nodes of the 0.03 rule and the 10 rCA1 circuits whose synapses need them more; none get fewer.
- The whole rCA1 circuit (456k cells) needs 54 nodes, more than the 20 of cell_a, and is refused; its node sets fit up to about 170k cells without replay, 110k with every CA3 source replayed.

What the model does not cover: recordings (their buffers are a few MB per rank, within the noise of the runs), runs much longer than 3 s (a 3 s run used 4% more than a 100 ms one), more than 16 ranks (the per-rank terms are extrapolated to 176 and 192), and circuits whose cells were not measured, which the floor covers.

---
tags:
  - circuit-simulation
---

# Circuit Simulation Memory Measurements

The data behind the resource estimate of circuit simulations ([Circuit Simulation Resources](circuit-simulation-resources.md)), from openbraininstitute/prod-circuit-simulation#265. Every number below was measured. The measurement scripts and the raw results (one JSON record per run, with its configuration, its counts, its memory over time and the peak of each rank) are kept with the ticket.

## Setup

- Images: `ghcr.io/openbraininstitute/neurodamus:4.2.11` (NEURON 9.0.0+g2ac5cc7, libsonata 0.2.2) and `:4.3.0` (NEURON 9.1.0.dev0+g1a6d545, libsonata 0.2.4, what `launch_scripts` pins), Open MPI 5.0.7. They are the base of the launch-system runtime `python3.12-compiler-openmpi5-neuron9-neurodamus`.
- Mechanisms compiled in each image with `neurodamus-compile-mods --with-internal-mods` and the image's `neurodamus-nrnivmodl`, as launch-system does.
- Launched as launch-system's `helpers/run_simulation.py` does: `mpirun -n R special -mpi -python $NEURODAMUS_PYTHON/init.py --configFile=...`, with no other neurodamus option. In production R is the number of cores of the nodes.
- Circuits: `rCA1-SLICE-L0.90-THICK300` (19k synapses per cell, 92% from the CA3 projection) and SSCX `nbS1-HEX0-L4` (2.4k synapses per cell), random cells with a fixed seed. Simulation configs as obi-one writes them (the conditions of the CA1 job `01a1cb34`).
- Replay: a SONATA spike file with a random fraction of the sources of the CA3 (or VPM and POm) population, 1 to 50 spikes each.
- LFP: electrode files of the layout neurodamus reads (`<population>/node_ids`, `<population>/offsets`, `electrodes/<population>/scaling_factors`), one row per segment of each simulated cell as neurodamus builds it.
- One container per run. Memory is the anonymous and shared memory of the container's cgroup (what the OOM killer counts, page cache excluded), sampled every 0.1 to 0.2 s, minus its baseline. The runs of large spike files also record the exact peak of each rank (`VmHWM`). Runs repeated in different sessions agree within 2 to 4%.

## Findings

1. Synapses dominate, and neurodamus creates all of them, replayed or not (4.2.11 and 4.3.0 do not skip the silent ones): 3.07 KB each.
2. Replay must be counted: each replayed connection adds 2.05 KB, its spike train and NetCon. Replaying every CA3 source costs 1.5 to 1.6 times no replay on rCA1; every thalamic source 3 to 7% on SSCX.
3. Large spike files cost on every rank of every node. Each rank reads all the spike files while it sets the replay up: a transient of 41.4 bytes per spike at the exact peak of a rank (16 ranks, 13.4M spikes). With few ranks, a rank's share of the model is larger than the transient and hides it. On a node of 192 ranks, 13.4M spikes (every CA3 source at 10 Hz for 5 s) take about 100 GB, whatever the number of nodes. Below about a million spikes it is lost in the noise.
4. An MPI rank costs 35 MB, 6.7 GB on a node of 192 ranks.
5. A cell costs 5.5 MB besides its synapses. SSCX costs 0.013 to 0.016 GB per cell.
6. NEURON and CoreNEURON peak within a few percent of each other: NEURON is 0.5 to 9% lower in 9 of 10 pairs and 2.5% higher in one, within the noise. CoreNEURON peaks while neurodamus writes its input, after freeing the NEURON model.
7. LFP costs 1.0 times the weights of the simulated cells (segments × electrodes × 8 bytes) plus about 7 MB per rank, summed or per cell alike. Only CoreNEURON computes it: neurodamus 4.2.11 and 4.3.0 skip LFP reports under NEURON.
8. Reports of the soma or of all compartments add nothing measurable: they go through a buffer of a few MB per rank.
9. A run of 3,000 ms uses 4% more than one of 100 ms.
10. neurodamus 4.3.0 with NEURON 9.1.0.dev0 uses the memory of 4.2.11 within 0.5% in 5 of 6 repeats, and 6.5% more in one.

## Measurements

### Replay: rCA1 slice, CoreNEURON, 8 ranks, 100 ms, 1 spike per replayed source (MB)

| Cells | Synapses | 0% replayed | 5% replayed | 25% replayed | 50% replayed | 100% replayed | 100% / 0% |
|---|---|---|---|---|---|---|---|
| 16 | 288,471 | 1,279 | 1,306 | 1,427 | 1,579 | 1,895 | 1.48 |
| 48 | 934,490 | 3,246 | 3,383 | 3,736 | 4,229 | 4,970 | 1.53 |
| 128 | 2,593,724 | 9,127 | 9,440 | 10,320 | 11,768 | 14,669 | 1.61 |

### NEURON against CoreNEURON: rCA1 slice, 48 cells, 8 ranks (MB)

| CA3 replayed | CoreNEURON | NEURON | NEURON / CoreNEURON |
|---|---|---|---|
| 0% | 3,246 | 3,155 | 0.972 |
| 5% | 3,383 | 3,246 | 0.959 |
| 25% | 3,736 | 3,589 | 0.961 |
| 50% | 4,229 | 4,066 | 0.962 |
| 100% | 4,970 | 5,070 | 1.020 |
| SSCX 400 cells, 0% | 5,218 | 4,868 | 0.933 |
| SSCX 400 cells, 100% | 5,566 | 5,086 | 0.914 |

### SSCX nbS1-HEX0-L4, CoreNEURON, 8 ranks, 100 ms (MB)

| Cells | Synapses | No replay | All VPM and POm sources replayed | GB per cell |
|---|---|---|---|---|
| 100 | 242,984 | 1,641 | 1,721 | 0.0160 |
| 400 | 938,181 | 5,218 | 5,566 | 0.0127 |
| 1200 | 2,940,020 | 16,327 | 16,797 | 0.0133 |

### MPI ranks: rCA1, 48 cells, 5% replay, CoreNEURON (MB)

| Ranks | Peak |
|---|---|
| 1 | 3,304 |
| 2 | 3,324 |
| 4 | 3,301 |
| 8 | 3,464 |
| 16 | 3,810 |

### Large spike files: rCA1, 48 cells, every CA3 source replayed, 100 ms, sampled every 0.1 s (MB)

Each rank reads the whole spike file. Its largest rank went from 560 to 1,077 MB with 16 ranks for 13.1M more spikes: 41.4 bytes per spike per rank. With 2 ranks the rank's share of the model is larger than the transient and hides it.

| Ranks | Spikes per source | Spikes | Job peak (sampled) | Sum of rank peaks (VmHWM) | Largest rank peak (VmHWM) |
|---|---|---|---|---|---|
| 2 | 1 | 267,238 | 5,169 | 5,281 | 2,666 |
| 2 | 50 | 13,361,900 | 5,485 | 5,596 | 2,834 |
| 8 | 50 | 13,361,900 | 7,796 | 9,180 | 1,168 |
| 16 | 1 | 267,238 | 5,728 | 6,712 | 560 |
| 16 | 50 | 13,361,900 | 12,182 | 16,509 | 1,077 |

### Spikes at 5% replay: rCA1, 48 cells, 8 ranks, 1,000 ms (MB)

| Spikes per source | Peak |
|---|---|
| 1 | 3,498 |
| 10 | 3,401 |
| 50 | 3,469 |

### Recordings: rCA1, 48 cells, 5% replay, 8 ranks, 1,000 ms (MB)

| Report | CoreNEURON | NEURON |
|---|---|---|
| none | 3,467 | 3,304 |
| soma | 3,402 | 3,278 |
| all_compartments | 3,399 | 3,341 |

### Run length: rCA1, 48 cells, 5% replay, CoreNEURON, 8 ranks (MB)

| tstop (ms) | Peak |
|---|---|
| 100 | 3,394 |
| 1000 | 3,418 |
| 3000 | 3,526 |

### LFP: neurodamus 4.3.0, CoreNEURON, 8 ranks, 1,000 ms (MB)

| Run | Electrodes | Method | Weights of the simulated cells | Peak | Added by LFP |
|---|---|---|---|---|---|
| lfp430_n48_none | 0 | - | 0 | 3,399 | - |
| lfp430_n48_sum_e16 | 16 | summed | 3 | 3,459 | 60 |
| lfp430_n48_bycell_e16 | 16 | per cell | 3 | 3,429 | 30 |
| lfp430_n48_sum_e128 | 128 | summed | 23 | 3,487 | 89 |
| lfp430_n48_sum_e384 | 384 | summed | 70 | 3,527 | 128 |
| lfp430_n48_bycell_e384 | 384 | per cell | 70 | 3,531 | 132 |
| lfp430_n48_sum_e1024 | 1024 | summed | 186 | 3,640 | 242 |
| lfp430_n128_none | 0 | - | 0 | 9,407 | - |
| lfp430_n128_sum_e384 | 384 | summed | 198 | 9,695 | 287 |
| lfp430_sscx_n400_none | 0 | - | 0 | 5,264 | - |
| lfp430_sscx_n400_sum_e384 | 384 | summed | 347 | 5,710 | 446 |

### neurodamus 4.3.0 / NEURON 9.1.0.dev0 against 4.2.11 / NEURON 9.0.0 (MB)

| Run | 4.2.11 | 4.3.0 | 4.3.0 / 4.2.11 |
|---|---|---|---|
| replay_core_n48_f0.05 | 3,383 | 3,396 | 1.004 |
| replay_core_n48_f1.0 | 4,970 | 5,294 | 1.065 |
| replay_core_n128_f0.0 | 9,127 | 9,087 | 0.996 |
| replay_core_n128_f1.0 | 14,669 | 14,691 | 1.002 |
| sscx_core_n400_f0.0 | 5,218 | 5,212 | 0.999 |
| replay_nrn_n48_f0.05 | 3,246 | 3,246 | 1.000 |

### Held out of the first fit: larger runs (MB)

| Run | Cells | Synapses | Ranks | Peak |
|---|---|---|---|---|
| large_core_n192_f1.0 | 192 | 3,657,453 | 16 | 20,493 |
| large_core_n256_f0.05 | 256 | 4,861,280 | 16 | 17,579 |

## Model

Fitted with non-negative least squares on relative errors over all the runs but three superseded ones (both images, both simulators), with the spike term fixed at the exact per-rank value:

| Term | Cost | Paid |
|---|---|---|
| MPI rank | 34.9 MB | on every node |
| Replay spike, per rank | 41.4 bytes | on every node |
| Rank, with LFP | 6.5 MB | on every node |
| Cell | 5.55 MB | split over the nodes |
| Synapse | 3.07 KB | split over the nodes |
| Replayed connection (counted per replayed synapse) | 2.05 KB | split over the nodes |
| LFP weights of the simulated cells | 1.04 times | split over the nodes |

With a margin of 1.15 (the largest measured peak is 1.09 times the fit), 90% of a node's memory for the simulation and a floor of 0.03 GB per cell (the rule SSCX ran with; the 0.025 GB per cell of the production runs behind it is about twice what was measured here, and the gap is not explained):

```
per_node = 1.15 * ranks_per_node * (34.9 MB + 41.4 B * spikes + 6.5 MB if LFP)
split    = 1.15 * (5.55 MB * cells + 3.07 KB * synapses + 2.05 KB * replayed synapses + 1.04 * LFP weights)
nodes    = max(ceil(split / (0.9 * node_memory - per_node)), ceil(0.03 GB * cells / node_memory))
```

Spike inputs for which `per_node` exceeds the usable memory of a node, and simulations needing more nodes than an instance type offers, are refused with an error that says why.

### Every run against the model

| Run | Image | Sim | Ranks | Cells | Synapses | Replayed conn. | Spikes | tstop | Reports | LFP weights MB | Peak MB | Sum of rank peaks MB | Model MB | Peak/Model |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hwm_spikes_n48_f1.0_k1_r16 | 4.2.11 | CORENEURON | 16 | 48 | 934,490 | 821,356 | 267,238 | 100 | - | 0 | 5,728 | 6,712 | 5,436 | 1.054 |
| hwm_spikes_n48_f1.0_k1_r2 | 4.2.11 | CORENEURON | 2 | 48 | 934,490 | 821,356 | 267,238 | 100 | - | 0 | 5,169 | 5,281 | 4,800 | 1.077 |
| hwm_spikes_n48_f1.0_k50_r16 | 4.2.11 | CORENEURON | 16 | 48 | 934,490 | 821,356 | 13,361,900 | 100 | - | 0 | 12,182 | 16,509 | 13,708 | 0.889 |
| hwm_spikes_n48_f1.0_k50_r2 | 4.2.11 | CORENEURON | 2 | 48 | 934,490 | 821,356 | 13,361,900 | 100 | - | 0 | 5,485 | 5,596 | 5,834 | 0.940 |
| hwm_spikes_n48_f1.0_k50_r8 | 4.2.11 | CORENEURON | 8 | 48 | 934,490 | 821,356 | 13,361,900 | 100 | - | 0 | 7,796 | 9,180 | 9,208 | 0.847 |
| large_core_n192_f1.0 | 4.2.11 | CORENEURON | 16 | 192 | 3,657,453 | 3,235,824 | 267,238 | 100 | - | 0 | 20,493 | - | 19,222 | 1.066 |
| large_core_n256_f0.05 | 4.2.11 | CORENEURON | 16 | 256 | 4,861,280 | 216,468 | 13,362 | 100 | - | 0 | 17,579 | - | 16,977 | 1.035 |
| lfp430_n128_none | 4.3.0 | CORENEURON | 8 | 128 | 2,593,724 | 115,119 | 13,362 | 1000 | - | 0 | 9,407 | - | 8,991 | 1.046 |
| lfp430_n128_sum_e384 | 4.3.0 | CORENEURON | 8 | 128 | 2,593,724 | 115,119 | 13,362 | 1000 | - | 198 | 9,695 | - | 9,248 | 1.048 |
| lfp430_n48_bycell_e16 | 4.3.0 | CORENEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 1000 | - | 3 | 3,429 | - | 3,485 | 0.984 |
| lfp430_n48_bycell_e384 | 4.3.0 | CORENEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 1000 | - | 70 | 3,531 | - | 3,555 | 0.993 |
| lfp430_n48_none | 4.3.0 | CORENEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 1000 | - | 0 | 3,399 | 4,016 | 3,431 | 0.991 |
| lfp430_n48_sum_e1024 | 4.3.0 | CORENEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 1000 | - | 186 | 3,640 | - | 3,676 | 0.990 |
| lfp430_n48_sum_e128 | 4.3.0 | CORENEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 1000 | - | 23 | 3,487 | - | 3,507 | 0.995 |
| lfp430_n48_sum_e16 | 4.3.0 | CORENEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 1000 | - | 3 | 3,459 | - | 3,485 | 0.992 |
| lfp430_n48_sum_e384 | 4.3.0 | CORENEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 1000 | - | 70 | 3,527 | - | 3,555 | 0.992 |
| lfp_smoke_n4_e16 | 4.3.0 | CORENEURON | 2 | 4 | 100,191 | 4,531 | 13,362 | 20 | - | 0 | 423 | - | 415 | 1.019 |
| ranks_n48_f0.05_r1 | 4.2.11 | CORENEURON | 1 | 48 | 934,490 | 41,269 | 13,362 | 100 | - | 0 | 3,304 | - | 3,183 | 1.038 |
| ranks_n48_f0.05_r16 | 4.2.11 | CORENEURON | 16 | 48 | 934,490 | 41,269 | 13,362 | 100 | - | 0 | 3,810 | - | 3,714 | 1.026 |
| ranks_n48_f0.05_r2 | 4.2.11 | CORENEURON | 2 | 48 | 934,490 | 41,269 | 13,362 | 100 | - | 0 | 3,324 | - | 3,218 | 1.033 |
| ranks_n48_f0.05_r4 | 4.2.11 | CORENEURON | 4 | 48 | 934,490 | 41,269 | 13,362 | 100 | - | 0 | 3,301 | 3,642 | 3,289 | 1.004 |
| ranks_n48_f0.05_r8 | 4.2.11 | CORENEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 100 | - | 0 | 3,464 | - | 3,431 | 1.010 |
| ranks_n48_f1.0_k10_r16 | 4.2.11 | CORENEURON | 16 | 48 | 934,490 | 821,356 | 2,672,380 | 1000 | - | 0 | 5,882 | - | 6,956 | 0.846 |
| ranks_n48_f1.0_k10_r2 | 4.2.11 | CORENEURON | 2 | 48 | 934,490 | 821,356 | 2,672,380 | 1000 | - | 0 | 5,220 | - | 4,989 | 1.046 |
| replay_core_n128_f0.0 | 4.2.11 | CORENEURON | 8 | 128 | 2,593,724 | 0 | 0 | 100 | - | 0 | 9,127 | - | 8,756 | 1.042 |
| replay_core_n128_f0.05 | 4.2.11 | CORENEURON | 8 | 128 | 2,593,724 | 115,119 | 13,362 | 100 | - | 0 | 9,440 | - | 8,991 | 1.050 |
| replay_core_n128_f0.25 | 4.2.11 | CORENEURON | 8 | 128 | 2,593,724 | 577,005 | 66,810 | 100 | - | 0 | 10,320 | - | 9,932 | 1.039 |
| replay_core_n128_f0.5 | 4.2.11 | CORENEURON | 8 | 128 | 2,593,724 | 1,156,391 | 133,619 | 100 | - | 0 | 11,768 | - | 11,113 | 1.059 |
| replay_core_n128_f1.0 | 4.2.11 | CORENEURON | 8 | 128 | 2,593,724 | 2,312,787 | 267,238 | 100 | - | 0 | 14,669 | - | 13,470 | 1.089 |
| replay_core_n16_f0.0 | 4.2.11 | CORENEURON | 8 | 16 | 288,471 | 0 | 0 | 100 | - | 0 | 1,279 | - | 1,232 | 1.038 |
| replay_core_n16_f0.05 | 4.2.11 | CORENEURON | 8 | 16 | 288,471 | 12,731 | 13,362 | 100 | - | 0 | 1,306 | - | 1,262 | 1.035 |
| replay_core_n16_f0.25 | 4.2.11 | CORENEURON | 8 | 16 | 288,471 | 64,153 | 66,810 | 100 | - | 0 | 1,427 | - | 1,381 | 1.033 |
| replay_core_n16_f0.5 | 4.2.11 | CORENEURON | 8 | 16 | 288,471 | 128,971 | 133,619 | 100 | - | 0 | 1,579 | - | 1,532 | 1.030 |
| replay_core_n16_f1.0 | 4.2.11 | CORENEURON | 8 | 16 | 288,471 | 258,338 | 267,238 | 100 | - | 0 | 1,895 | - | 1,833 | 1.034 |
| replay_core_n48_f0.0 | 4.2.11 | CORENEURON | 8 | 48 | 934,490 | 0 | 0 | 100 | - | 0 | 3,246 | - | 3,344 | 0.971 |
| replay_core_n48_f0.05 | 4.2.11 | CORENEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 100 | - | 0 | 3,383 | - | 3,431 | 0.986 |
| replay_core_n48_f0.25 | 4.2.11 | CORENEURON | 8 | 48 | 934,490 | 205,977 | 66,810 | 100 | - | 0 | 3,736 | - | 3,777 | 0.989 |
| replay_core_n48_f0.5 | 4.2.11 | CORENEURON | 8 | 48 | 934,490 | 410,928 | 133,619 | 100 | - | 0 | 4,229 | - | 4,209 | 1.005 |
| replay_core_n48_f1.0 | 4.2.11 | CORENEURON | 8 | 48 | 934,490 | 821,356 | 267,238 | 100 | - | 0 | 4,970 | - | 5,072 | 0.980 |
| replay_nrn_n16_f0.05 | 4.2.11 | NEURON | 8 | 16 | 288,471 | 12,731 | 13,362 | 100 | - | 0 | 1,277 | - | 1,262 | 1.012 |
| replay_nrn_n16_f1.0 | 4.2.11 | NEURON | 8 | 16 | 288,471 | 258,338 | 267,238 | 100 | - | 0 | 1,849 | - | 1,833 | 1.008 |
| replay_nrn_n48_f0.0 | 4.2.11 | NEURON | 8 | 48 | 934,490 | 0 | 0 | 100 | - | 0 | 3,155 | 3,575 | 3,344 | 0.944 |
| replay_nrn_n48_f0.05 | 4.2.11 | NEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 100 | - | 0 | 3,246 | 3,669 | 3,431 | 0.946 |
| replay_nrn_n48_f0.25 | 4.2.11 | NEURON | 8 | 48 | 934,490 | 205,977 | 66,810 | 100 | - | 0 | 3,589 | - | 3,777 | 0.950 |
| replay_nrn_n48_f0.5 | 4.2.11 | NEURON | 8 | 48 | 934,490 | 410,928 | 133,619 | 100 | - | 0 | 4,066 | - | 4,209 | 0.966 |
| replay_nrn_n48_f1.0 | 4.2.11 | NEURON | 8 | 48 | 934,490 | 821,356 | 267,238 | 100 | - | 0 | 5,070 | - | 5,072 | 0.999 |
| reports_coreneuron_all_compartments | 4.2.11 | CORENEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 1000 | all_compartments | 0 | 3,399 | - | 3,431 | 0.991 |
| reports_coreneuron_none | 4.2.11 | CORENEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 1000 | - | 0 | 3,467 | 4,026 | 3,431 | 1.011 |
| reports_coreneuron_soma | 4.2.11 | CORENEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 1000 | soma | 0 | 3,402 | - | 3,431 | 0.992 |
| reports_neuron_all_compartments | 4.2.11 | NEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 1000 | all_compartments | 0 | 3,341 | - | 3,431 | 0.974 |
| reports_neuron_none | 4.2.11 | NEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 1000 | - | 0 | 3,304 | 3,725 | 3,431 | 0.963 |
| reports_neuron_soma | 4.2.11 | NEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 1000 | soma | 0 | 3,278 | - | 3,431 | 0.955 |
| s430_core_n128_f0.0 | 4.3.0 | CORENEURON | 8 | 128 | 2,593,724 | 0 | 0 | 100 | - | 0 | 9,087 | - | 8,756 | 1.038 |
| s430_core_n128_f1.0 | 4.3.0 | CORENEURON | 8 | 128 | 2,593,724 | 2,312,787 | 267,238 | 100 | - | 0 | 14,691 | - | 13,470 | 1.091 |
| s430_core_n48_f0.05 | 4.3.0 | CORENEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 100 | - | 0 | 3,396 | 4,016 | 3,431 | 0.990 |
| s430_core_n48_f1.0 | 4.3.0 | CORENEURON | 8 | 48 | 934,490 | 821,356 | 267,238 | 100 | - | 0 | 5,294 | - | 5,072 | 1.044 |
| s430_nrn_n48_f0.05 | 4.3.0 | NEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 100 | - | 0 | 3,246 | 3,667 | 3,431 | 0.946 |
| spikes_n48_f0.05_k1 | 4.2.11 | CORENEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 1000 | - | 0 | 3,498 | 4,028 | 3,431 | 1.020 |
| spikes_n48_f0.05_k10 | 4.2.11 | CORENEURON | 8 | 48 | 934,490 | 41,269 | 133,620 | 1000 | - | 0 | 3,401 | - | 3,469 | 0.981 |
| spikes_n48_f0.05_k50 | 4.2.11 | CORENEURON | 8 | 48 | 934,490 | 41,269 | 668,100 | 1000 | - | 0 | 3,469 | - | 3,638 | 0.954 |
| spikes_n48_f1.0_k1 | 4.2.11 | CORENEURON | 8 | 48 | 934,490 | 821,356 | 267,238 | 1000 | - | 0 | 5,190 | - | 5,072 | 1.023 |
| spikes_n48_f1.0_k10 | 4.2.11 | CORENEURON | 8 | 48 | 934,490 | 821,356 | 2,672,380 | 1000 | - | 0 | 5,289 | - | 5,832 | 0.907 |
| tstop_n48_f0.05_t100 | 4.2.11 | CORENEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 100 | - | 0 | 3,394 | 4,027 | 3,431 | 0.989 |
| tstop_n48_f0.05_t1000 | 4.2.11 | CORENEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 1000 | - | 0 | 3,418 | 4,024 | 3,431 | 0.996 |
| tstop_n48_f0.05_t3000 | 4.2.11 | CORENEURON | 8 | 48 | 934,490 | 41,269 | 13,362 | 3000 | - | 0 | 3,526 | 4,024 | 3,431 | 1.028 |
| lfp430_sscx_n400_none | 4.3.0 | CORENEURON | 8 | 400 | 938,181 | 0 | 0 | 1000 | - | 0 | 5,264 | - | 5,308 | 0.992 |
| lfp430_sscx_n400_sum_e384 | 4.3.0 | CORENEURON | 8 | 400 | 938,181 | 0 | 0 | 1000 | - | 347 | 5,710 | - | 5,720 | 0.998 |
| s430_sscx_core_n400_f0.0 | 4.3.0 | CORENEURON | 8 | 400 | 938,181 | 0 | 0 | 100 | - | 0 | 5,212 | - | 5,308 | 0.982 |
| sscx_core_n100_f0.0 | 4.2.11 | CORENEURON | 8 | 100 | 242,984 | 0 | 0 | 100 | - | 0 | 1,641 | - | 1,562 | 1.050 |
| sscx_core_n100_f1.0 | 4.2.11 | CORENEURON | 8 | 100 | 242,984 | 10,584 | 5,109 | 100 | - | 0 | 1,721 | - | 1,585 | 1.086 |
| sscx_core_n1200_f0.0 | 4.2.11 | CORENEURON | 8 | 1200 | 2,940,020 | 0 | 0 | 100 | - | 0 | 16,327 | - | 15,742 | 1.037 |
| sscx_core_n1200_f1.0 | 4.2.11 | CORENEURON | 8 | 1200 | 2,940,020 | 123,408 | 5,109 | 100 | - | 0 | 16,797 | - | 15,991 | 1.050 |
| sscx_core_n400_f0.0 | 4.2.11 | CORENEURON | 8 | 400 | 938,181 | 0 | 0 | 100 | - | 0 | 5,218 | - | 5,308 | 0.983 |
| sscx_core_n400_f1.0 | 4.2.11 | CORENEURON | 8 | 400 | 938,181 | 40,485 | 5,109 | 100 | - | 0 | 5,566 | - | 5,391 | 1.032 |
| sscx_nrn_n400_f0.0 | 4.2.11 | NEURON | 8 | 400 | 938,181 | 0 | 0 | 100 | - | 0 | 4,868 | - | 5,308 | 0.917 |
| sscx_nrn_n400_f1.0 | 4.2.11 | NEURON | 8 | 400 | 938,181 | 40,485 | 5,109 | 100 | - | 0 | 5,086 | - | 5,391 | 0.943 |

## Against production

The CA1 job `01a1cb34` (9,587 cells, 219.1M synapses, 5.4% of the CA3 sources replayed with one spike each, 192 ranks on cell_a) is the production check. The fit without margin gives it 722 GB on one node; it ran out of memory there at about 4 GB per rank, about 768 GB, 1.06 times the fit. With the margin the model needs 830 GB on one node, more than the 691 GB usable, and gives it 2 nodes, the 2 it ran on.

Nodes the model gives real cases, against the old rules (the replayed synapses are the actual ones; obi-one records 2.5 times the replayed share, which adds about 44 GB to the CA1 job and still gives 2 nodes):

### cell_a large (hpc7a.96xlarge): 768 GB, 192 ranks per node

| Case | Cells | Synapses | Replayed | Spikes | Per node GB | Split GB | Nodes (model) | Nodes (with 0.03 floor) | Old 0.03 | Main 0.09 | Measured |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CA1 job 01a1cb34 (L0.69 slice, 5.4% CA3 replayed, 1 spike per source) | 9,587 | 219.1M | 10.9M | 14,548 | 7.6 | 822 | 2 | 2 | 1 | 2 | OOM on 1 node, ran on 2 |
| same circuit, 100% CA3 replay, 1 spike | 9,587 | 219.1M | 200.3M | 267,238 | 9.8 | 1,248 | 2 | 2 | 1 | 2 | - |
| same circuit, 100% CA3 replay, 10 Hz for 5 s (50 spikes) | 9,587 | 219.1M | 200.3M | 13,361,900 | 121.3 | 1,248 | 3 | 3 | 1 | 2 | - |
| rCA1 L0.90 slice, 5% replay | 4,917 | 94.1M | 4.3M | 13,362 | 7.6 | 357 | 1 | 1 | 1 | 1 | - |
| rCA1 L0.90 slice, 100% replay | 4,917 | 94.1M | 86.2M | 267,238 | 9.8 | 541 | 1 | 1 | 1 | 1 | - |
| SSCX nbS1-HEX0 (30,190 cells, 2,650 syn/cell), no replay | 30,190 | 80.0M | 0.0M | 0 | 7.5 | 458 | 1 | 2 | 2 | 4 | - |
| SSCX nbS1-O1 (211,712 cells), full thalamic replay | 211,712 | 560.6M | 39.2M | 300,000 | 10.1 | 3,295 | 5 | 9 | 9 | 25 | - |
| SSCX nbS1-O1, 10 Hz for 2 s on all thalamic sources | 211,712 | 560.6M | 39.2M | 6,000,000 | 58.6 | 3,295 | 6 | 9 | 9 | 25 | - |
| rCA1 full (456k cells), 5% replay | 456,378 | 9,943.1M | 457.4M | 13,362 | 7.6 | 37,351 | 55 | 55 | 18 | 54 | - |

### cell_b large (HB176rs_v4): 788 GB, 176 ranks per node

| Case | Cells | Synapses | Replayed | Spikes | Per node GB | Split GB | Nodes (model) | Nodes (with 0.03 floor) | Old 0.03 | Main 0.09 | Measured |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CA1 job 01a1cb34 (L0.69 slice, 5.4% CA3 replayed, 1 spike per source) | 9,587 | 219.1M | 10.9M | 14,548 | 7.0 | 822 | 2 | 2 | 1 | 2 | OOM on 1 node, ran on 2 |
| same circuit, 100% CA3 replay, 1 spike | 9,587 | 219.1M | 200.3M | 267,238 | 9.0 | 1,248 | 2 | 2 | 1 | 2 | - |
| same circuit, 100% CA3 replay, 10 Hz for 5 s (50 spikes) | 9,587 | 219.1M | 200.3M | 13,361,900 | 111.2 | 1,248 | 3 | 3 | 1 | 2 | - |
| rCA1 L0.90 slice, 5% replay | 4,917 | 94.1M | 4.3M | 13,362 | 7.0 | 357 | 1 | 1 | 1 | 1 | - |
| rCA1 L0.90 slice, 100% replay | 4,917 | 94.1M | 86.2M | 267,238 | 9.0 | 541 | 1 | 1 | 1 | 1 | - |
| SSCX nbS1-HEX0 (30,190 cells, 2,650 syn/cell), no replay | 30,190 | 80.0M | 0.0M | 0 | 6.9 | 458 | 1 | 2 | 2 | 4 | - |
| SSCX nbS1-O1 (211,712 cells), full thalamic replay | 211,712 | 560.6M | 39.2M | 300,000 | 9.2 | 3,295 | 5 | 9 | 9 | 25 | - |
| SSCX nbS1-O1, 10 Hz for 2 s on all thalamic sources | 211,712 | 560.6M | 39.2M | 6,000,000 | 53.7 | 3,295 | 6 | 9 | 9 | 25 | - |
| rCA1 full (456k cells), 5% replay | 456,378 | 9,943.1M | 457.4M | 13,362 | 7.0 | 37,351 | 54 | 54 | 18 | 53 | - |

## Nodes available

cell_a (aws-terraform-deployment `staging`, `launch_system/pcs.tf` and `main.tf`): at most 20 `hpc7a.96xlarge` in `pcs-queue-large`, with no fallback instance type, and 12 `t3a.xlarge` in `pcs-queue-small`; both reserve 750 MB per node for Slurm. The 20 nodes are shared by every job running at once. cell_b: the Azure batch pool of `Standard_HB176rs_v4` autoscales with the active tasks, with no maximum in its formula; its limit is the subscription quota.

- The 0.09 GB per cell of `main` asks more than 20 nodes for 11 circuits a user can simulate whole: nbS1-O1 and its 7 variants (25), the human microcircuit (30), the 18-hex long slice (48). The 0.03 rule and the new estimate give them 9, 10 and 16.
- The new estimate exceeds 20 nodes only for the whole rCA1 circuit (54, 57 with 5% of CA3 replayed, 85 with all of it), which the estimator therefore refuses on cell_a. The 0.03 rule gave it 18, in which it would run out of memory. rCA1 node sets fit 20 nodes up to about 172k cells without replay, 160k with 5% of CA3 replayed and 109k with all of it.

## Every circuit of entitycore, simulated whole

Nodes of cell_a for a whole-circuit simulation of each of the 122 distinct circuits of more than 20 cells in staging and production on 2026-11-26, from the estimator itself, before it refused requests above the nodes available. Against the 0.03 rule, the new estimate gives the same nodes to 112 (every SSCX, thalamus, MICrONS, H01, Allen and synaptome circuit, through the floor) and more to the 10 rCA1 circuits whose synapses need them, 20 with every virtual source replayed; fewer to none. "5% replayed" replays 5% of the sources of every virtual population, recorded as 12.5% of their synapses.

| Circuit | Instance | Cells | Syn/cell | Model GB/cell (no floor) | 0.03 (old SSCX) | 0.09 (main) | New, no replay | New, 5% replayed | New, all replayed |
|---|---|---|---|---|---|---|---|---|---|
| rCA1 | large | 456,378 | 21,787 | 0.0796 | 18 | 54 | 54 | 57 | 85 |
| nbS1-longSlice-18HexColumns | large | 403,634 | 1,803 | 0.0123 | 16 | 48 | 16 | 16 | 16 |
| Human_Stochastic_Microcircuit | large | 250,699 | 1,174 | 0.0102 | 10 | 30 | 10 | 10 | 10 |
| nbS1-O1-beta-DD | large | 211,712 | 2,146 | 0.0135 | 9 | 25 | 9 | 9 | 9 |
| nbS1-O1-beta | large | 211,712 | 2,155 | 0.0135 | 9 | 25 | 9 | 9 | 9 |
| nbS1-O1-SM | large | 211,712 | 2,647 | 0.0151 | 9 | 25 | 9 | 9 | 9 |
| nbS1-O1 (legacy) | large | 211,712 | 2,648 | 0.0151 | 9 | 25 | 9 | 9 | 9 |
| nbS1-O1-beta-POS | large | 211,712 | 2,155 | 0.0135 | 9 | 25 | 9 | 9 | 9 |
| nbS1-O1-beta-BIP | large | 211,712 | 2,150 | 0.0135 | 9 | 25 | 9 | 9 | 9 |
| nbS1-O1 | large | 211,712 | 2,648 | 0.0151 | 9 | 25 | 9 | 9 | 9 |
| nbS1-O1-beta-OFF | large | 211,712 | 2,151 | 0.0135 | 9 | 25 | 9 | 9 | 9 |
| nbS1-O1-beta-ER | large | 211,712 | 2,134 | 0.0134 | 9 | 25 | 9 | 9 | 9 |
| MaleCNS-v1.0-NEURON-v1 | large | 164,606 | 753 | 0.0088 | 7 | 20 | 7 | 7 | 7 |
| BBP thalamoreticular circuit | large | 100,765 | 619 | 0.0083 | 4 | 12 | 4 | 4 | 4 |
| MICrONS_v1 | large | 50,948 | 292 | 0.0072 | 2 | 6 | 2 | 2 | 2 |
| nbS1-Cylinder-Hex0-0.045 | large | 45,462 | 2,657 | 0.0152 | 2 | 6 | 2 | 2 | 2 |
| nbS1-HEX2 | large | 31,338 | 2,655 | 0.0152 | 2 | 4 | 2 | 2 | 2 |
| nbS1-HEX6 | large | 30,444 | 2,640 | 0.0151 | 2 | 4 | 2 | 2 | 2 |
| nbS1-HEX4 | large | 30,249 | 2,661 | 0.0152 | 2 | 4 | 2 | 2 | 2 |
| nbS1-HEX0-beta-DD | large | 30,190 | 2,470 | 0.0146 | 2 | 4 | 2 | 2 | 2 |
| nbS1-HEX0-beta-POS | large | 30,190 | 2,533 | 0.0148 | 2 | 4 | 2 | 2 | 2 |
| nbS1-HEX0-beta-ER | large | 30,190 | 2,382 | 0.0143 | 2 | 4 | 2 | 2 | 2 |
| nbS1-HEX0-beta-BIP | large | 30,190 | 2,500 | 0.0147 | 2 | 4 | 2 | 2 | 2 |
| nbS1-HEX0 | large | 30,190 | 2,650 | 0.0152 | 2 | 4 | 2 | 2 | 2 |
| nbS1-HEX0-beta-OFF | large | 30,190 | 2,506 | 0.0147 | 2 | 4 | 2 | 2 | 2 |
| nbS1-HEX0 (legacy) | large | 30,190 | 1,606 | 0.0116 | 2 | 4 | 2 | 2 | 2 |
| nbS1-HEX0-beta | large | 30,190 | 2,535 | 0.0148 | 2 | 4 | 2 | 2 | 2 |
| nbS1-HEX0-ModFix | large | 30,190 | 1,606 | 0.0116 | 2 | 4 | 2 | 2 | 2 |
| nbS1-HEX0 [remote-validation-workaround-test | large | 30,190 | 2,650 | 0.0152 | 2 | 4 | 2 | 2 | 2 |
| nbS1-HEX0 (synapse-parameterized) | large | 30,190 | 1,606 | 0.0116 | 2 | 4 | 2 | 2 | 2 |
| nbS1-HEX0 [release-2026.11.2-test] | large | 30,190 | 2,650 | 0.0152 | 2 | 4 | 2 | 2 | 2 |
| nbS1-midrange | large | 30,190 | 3,217 | 0.0171 | 2 | 4 | 2 | 2 | 2 |
| nbS1-HEX3 | large | 29,892 | 2,666 | 0.0152 | 2 | 4 | 2 | 2 | 2 |
| nbS1-HEX5 | large | 29,861 | 2,610 | 0.0150 | 2 | 4 | 2 | 2 | 2 |
| nbS1-HEX1 | large | 29,738 | 2,654 | 0.0152 | 2 | 4 | 2 | 2 | 2 |
| rCA1-SLICE-REF | large | 17,647 | 21,822 | 0.0797 | 1 | 3 | 3 | 3 | 4 |
| rCA1-SLICE-REF (synapse-parameterized) | large | 17,647 | 21,370 | 0.0782 | 1 | 3 | 3 | 3 | 4 |
| rCA1-SLICE-L0.37-THICK300 | large | 14,579 | 22,685 | 0.0826 | 1 | 2 | 2 | 2 | 3 |
| rCA1-SLICE-L0.16-THICK300 | large | 13,082 | 22,640 | 0.0825 | 1 | 2 | 2 | 2 | 3 |
| rCA1-SLICE-L0.48-THICK300 | large | 12,887 | 21,868 | 0.0799 | 1 | 2 | 2 | 2 | 3 |
| rCA1-SLICE-L0.27-THICK300 | large | 12,751 | 20,948 | 0.0768 | 1 | 2 | 2 | 2 | 3 |
| rCA1-SLICE-L0.59-THICK300 | large | 12,746 | 21,168 | 0.0775 | 1 | 2 | 2 | 2 | 3 |
| nbS1-HEX2-L6 | large | 12,025 | 2,371 | 0.0142 | 1 | 2 | 1 | 1 | 1 |
| nbS1-HEX0-L6 | large | 11,032 | 2,412 | 0.0144 | 1 | 2 | 1 | 1 | 1 |
| nbS1-HEX0-L6-remote-validation-test-prod | large | 11,032 | 2,412 | 0.0144 | 1 | 2 | 1 | 1 | 1 |
| nbS1-HEX0-L6 (synapse-parameterized) | large | 11,032 | 872 | 0.0092 | 1 | 2 | 1 | 1 | 1 |
| nbS1-HEX0-L6 [remote-validation-workaround-t | large | 11,032 | 2,412 | 0.0144 | 1 | 2 | 1 | 1 | 1 |
| nbS1-HEX0-L6 [release-2026.11.2-test] | large | 11,032 | 2,412 | 0.0144 | 1 | 2 | 1 | 1 | 1 |
| nbS1-HEX3-L6 | large | 10,799 | 2,403 | 0.0143 | 1 | 2 | 1 | 1 | 1 |
| nbS1-HEX6-L6 | large | 10,512 | 2,437 | 0.0144 | 1 | 2 | 1 | 1 | 1 |
| nbS1-HEX1-L6 | large | 10,182 | 2,416 | 0.0144 | 1 | 2 | 1 | 1 | 1 |
| nbS1-HEX5-L23 | large | 9,615 | 1,445 | 0.0111 | 1 | 2 | 1 | 1 | 1 |
| rCA1-SLICE-L0.69-THICK300 | large | 9,587 | 22,854 | 0.0832 | 1 | 2 | 2 | 2 | 2 |
| nbS1-HEX4-L6 | large | 9,579 | 2,464 | 0.0145 | 1 | 2 | 1 | 1 | 1 |
| nbS1-HEX4-L23 | large | 9,265 | 1,466 | 0.0112 | 1 | 2 | 1 | 1 | 1 |
| nbS1-HEX5-L6 | large | 8,932 | 2,502 | 0.0147 | 1 | 2 | 1 | 1 | 1 |
| nbS1-HEX6-L23 | large | 8,803 | 1,481 | 0.0112 | 1 | 2 | 1 | 1 | 1 |
| nbS1-HEX1-L23 | large | 8,552 | 1,481 | 0.0112 | 1 | 2 | 1 | 1 | 1 |
| nbS1-HEX2-L23 | large | 8,234 | 1,490 | 0.0113 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX3-L23 | large | 8,193 | 1,477 | 0.0112 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX0-L23 | large | 8,173 | 1,446 | 0.0111 | 1 | 1 | 1 | 1 | 1 |
| rCA1-SLICE-L0.80-THICK300 | large | 8,081 | 22,382 | 0.0816 | 1 | 1 | 1 | 2 | 2 |
| rCA1-CYLINDER-L0.8-RAD300 | large | 7,934 | 24,047 | 0.0872 | 1 | 1 | 2 | 2 | 2 |
| rCA1-CYLINDER-L0.7-RAD300 | large | 7,733 | 24,084 | 0.0873 | 1 | 1 | 1 | 2 | 2 |
| rCA1-CYLINDER-L0.3-RAD300 | large | 7,716 | 23,605 | 0.0857 | 1 | 1 | 1 | 2 | 2 |
| rCA1-SLICE-L0.05-THICK300 | large | 7,571 | 21,628 | 0.0791 | 1 | 1 | 1 | 1 | 2 |
| rCA1-CYLINDER-L0.1-RAD300 | large | 7,302 | 23,211 | 0.0844 | 1 | 1 | 1 | 1 | 2 |
| rCA1-CYLINDER-L0.9-RAD300 | large | 7,293 | 22,402 | 0.0817 | 1 | 1 | 1 | 1 | 2 |
| rCA1-CYLINDER-L0.4-RAD300 | large | 6,532 | 21,996 | 0.0803 | 1 | 1 | 1 | 1 | 2 |
| rCA1-CYLINDER-L0.6-RAD300 | large | 6,397 | 21,433 | 0.0784 | 1 | 1 | 1 | 1 | 2 |
| rCA1-CYLINDER-L0.5-RAD300 | large | 6,360 | 21,525 | 0.0787 | 1 | 1 | 1 | 1 | 2 |
| rCA1-CYLINDER-REF | large | 6,213 | 21,841 | 0.0798 | 1 | 1 | 1 | 1 | 2 |
| nbS1-HEX2-L5 | large | 5,963 | 5,185 | 0.0237 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX4-L5 | large | 5,897 | 5,300 | 0.0241 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX6-L5 | large | 5,878 | 5,125 | 0.0235 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX0-L5 | large | 5,824 | 5,140 | 0.0235 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX3-L5 | large | 5,820 | 5,234 | 0.0239 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX1-L5 | large | 5,818 | 5,217 | 0.0238 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX5-L5 | large | 5,658 | 5,196 | 0.0237 | 1 | 1 | 1 | 1 | 1 |
| rCA1-CYLINDER-L0.2-RAD300 | large | 5,461 | 18,935 | 0.0700 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX5-L4 | large | 5,183 | 2,344 | 0.0141 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX4-L4 | large | 5,030 | 2,365 | 0.0142 | 1 | 1 | 1 | 1 | 1 |
| rCA1-SLICE-L0.90-THICK300 | large | 4,917 | 19,136 | 0.0707 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX6-L4 | large | 4,902 | 2,342 | 0.0141 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX0-L4 | large | 4,870 | 2,372 | 0.0142 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX0-L4 (synapse-parameterized) | large | 4,870 | 781 | 0.0089 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX2-L4 | large | 4,795 | 2,375 | 0.0142 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX1-L4 | large | 4,767 | 2,345 | 0.0141 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX3-L4 | large | 4,716 | 2,344 | 0.0141 | 1 | 1 | 1 | 1 | 1 |
| H01_v1 | large | 3,684 | 36 | 0.0064 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX0-Cylinder-r75um | large | 3,185 | 702 | 0.0086 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX0 | large | 2,000 | 563 | 0.0081 | 1 | 1 | 1 | 1 | 1 |
| FlyWire-v783-whole-brain-MC-pilot-1pct | large | 1,379 | 3 | 0.0062 | 1 | 1 | 1 | 1 | 1 |
| MaleCNS-v1.0-NEURON-sugar-pathway-highres-v1 | large | 517 | 1,047 | 0.0098 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX4-L1 | large | 478 | 351 | 0.0074 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX5-L1 | large | 473 | 338 | 0.0074 | 1 | 1 | 1 | 1 | 1 |
| jdc-test-circuit | large | 473 | 338 | 0.0074 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX1-L1 | large | 419 | 334 | 0.0074 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX3-L1 | large | 364 | 342 | 0.0074 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX6-L1 | large | 349 | 330 | 0.0073 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX2-L1 | large | 321 | 316 | 0.0073 | 1 | 1 | 1 | 1 | 1 |
| nbS1 | large | 302 | 2,397 | 0.0143 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX0-L1 | large | 291 | 322 | 0.0073 | 1 | 1 | 1 | 1 | 1 |
| nbS1-HEX0-L1 (synapse-parameterized) | large | 291 | 101 | 0.0066 | 1 | 1 | 1 | 1 | 1 |
| FlyWire-v783-sugar-to-MN9-multicompartment | large | 243 | 560 | 0.0081 | 1 | 1 | 1 | 1 | 1 |
| SSCx-S1FL-L345-32cell-recurrentOFF-r6 | small | 32 | 3,084 | 0.0166 | 1 | 1 | 1 | 1 | 1 |
| SSCx-S1FL-L345-32cell-recurrentON-r6 | small | 32 | 3,170 | 0.0169 | 1 | 1 | 1 | 1 | 1 |
| SSCx hex0 30-cell L2/L3 strongly-recurrent s | small | 30 | 1,367 | 0.0108 | 1 | 1 | 1 | 1 | 1 |
| L2_L3_sphere_rossert_detailed_v4 | small | 30 | 1,411 | 0.0110 | 1 | 1 | 1 | 1 | 1 |
| L2_L3_sphere_recurrent_on_private | small | 30 | 1,411 | 0.0110 | 1 | 1 | 1 | 1 | 1 |
| L2_L3_sphere_single_compartment_v4 | small | 30 | 1,411 | 0.0110 | 1 | 1 | 1 | 1 | 1 |
| SSCx hex0 30-cell representative sub-circuit | small | 30 | 2,421 | 0.0144 | 1 | 1 | 1 | 1 | 1 |
| nbS1-Cylinder-Hex0 central tube (30 cells, L | small | 30 | 277 | 0.0072 | 1 | 1 | 1 | 1 | 1 |
| SSCx hex0 30-cell L2/L3 strongly-recurrent s | small | 30 | 1,367 | 0.0108 | 1 | 1 | 1 | 1 | 1 |
| SSCx hex0 30-cell L2/L3 strongly-recurrent s | small | 30 | 1,411 | 0.0110 | 1 | 1 | 1 | 1 | 1 |
| nbS1-Cylinder-Hex0 central tube (30 cells, L | small | 30 | 277 | 0.0072 | 1 | 1 | 1 | 1 | 1 |
| L2_L3_sphere_recurrent_off_private | small | 30 | 1,367 | 0.0108 | 1 | 1 | 1 | 1 | 1 |
| SSCx hex0 30-cell L2/L3 strongly-recurrent s | small | 30 | 1,411 | 0.0110 | 1 | 1 | 1 | 1 | 1 |
| L2_L3_sphere_rossert_gif_v4 | small | 30 | 1,411 | 0.0110 | 1 | 1 | 1 | 1 | 1 |
| L2_L3_sphere_rossert_gif_fixed_v5 | small | 30 | 1,411 | 0.0110 | 1 | 1 | 1 | 1 | 1 |
| nbS1-Cylinder-Hex0-0.045-sub30 | small | 30 | 277 | 0.0072 | 1 | 1 | 1 | 1 | 1 |
| SSCx hex0 30-cell representative sub-circuit | small | 30 | 2,421 | 0.0144 | 1 | 1 | 1 | 1 | 1 |

## The edge files of entitycore

All 2,926 Circuit entities of staging (2,556) and production (370) on 2026-11-26, read with `Client.open_file` and range requests, without downloading the edge files. Every edge population obi-one counts has a `target_to_source` index, and every edges file is sorted by target (at most 4 ranges per cell, median 1).

| Circuits | production | staging |
|---|---|---|
| Every edge population counted exactly | 292 | 2463 |
| Some edge population above 32 MB of index (nbS1, nbS1-midrange) | 2 | 2 |
| Index of a length other than the population (synaptomes) | 44 | 35 |
| No chemical edges onto biophysical cells | 12 | 46 |
| Empty `sonata_circuit` directory | 0 | 8 |
| No `sonata_circuit` asset | 20 | 2 |
| Total | 370 | 2556 |

| Edge populations obi-one counts | production | staging |
|---|---|---|
| With a `target_to_source` index | 940 | 7185 |
| Exact as stored | 887 | 7128 |
| Index rows beyond the population, all empty | 41 | 30 |
| Index shorter than the population | 5 | 20 |
| Index above 32 MB | 7 | 7 |
| Total | 940 | 7185 |

- The writer of the Multi-synaptome circuits leaves the last target cell out of `target_to_source`, and the edges onto it: libsonata, and so neurodamus, reads the afferents of a cell through this index, so those edges are probably not simulated either. obi-one counts those populations in total.
- The Afferent-synaptome circuits pad `target_to_source` with empty rows up to 19 and truncate `source_to_target` (24 rows for 2,927 sources). obi-one ignores the extra rows.
- nbS1 and nbS1-midrange (4.2M cells) have 68 MB of index per edge population, and are counted in total from the shape of `source_node_id`.

Uniform estimate against the exact count, over 371 populations of 100 cells or more (ratio below 1: the estimate is too low):

| Node set | Worst | 5th percentile |
|---|---|---|
| Random 10% of the cells | 0.53 | 0.81 |
| Random 1% | 0.22 | 0.52 |
| Contiguous 10% of the node ids (about one layer or m-type) | 0.29 | 0.46 |

One layer of an SSCX circuit holds up to 2.2 times the mean synapses per cell, hence the factor of 2.5 on the share of cells (and of sources) of a node set counted in total.

## Cost of the estimate

The first simulation of a circuit reads its edge indices in the API service (production, a fresh process per circuit). The next simulations of the circuit read nothing: the synapses per cell are cached, at most 16 circuits.

| Circuit | Cells | Staging the nodes (already done) | Reading the indices | Range requests | Added peak memory | Kept in cache |
|---|---|---|---|---|---|---|
| nbS1-HEX0-L4 | 4,870 | 9.6 s | 5.1 s | 16 | 7 MB | 0.07 MB |
| rCA1-SLICE-L0.69-THICK300 | 9,587 | 4.4 s | 4.5 s | 13 | 7 MB | 0.11 MB |
| nbS1-HEX0 | 30,190 | 14.7 s | 6.7 s | 19 | 10 MB | 0.46 MB |
| MICrONS_v1 | 50,948 | 12.8 s | 7.4 s | 22 | 12 MB | 0.58 MB |
| BBP thalamoreticular circuit | 100,765 | 7.1 s | 7.3 s | 21 | 16 MB | 1.15 MB |
| nbS1-O1 | 211,712 | 25.9 s | 10.4 s | 20 | 24 MB | 3.23 MB |
| nbS1-longSlice-18HexColumns | 403,634 | 6.2 s | 7.8 s | 20 | 40 MB | 4.62 MB |
| rCA1 | 456,378 | 26.4 s | 8.9 s | 13 | 43 MB | 3.48 MB |
| nbS1 | 4,234,929 | 61.5 s | 4.0 s | 12 | 5 MB | 0.0 MB |

Counting the replay spike files at generation takes 0.09 s and 23 MB for 13.4M spikes (a file of 204 MB). At launch the estimator makes the `get_entity` it made before, plus two per LFP recording array.

## Limits

- One machine, up to 16 ranks: the per-rank terms are extrapolated to 176 and 192 ranks per node, and the inter-node MPI buffers of production are not in the measurements. The CA1 job is the only production check.
- Two circuits were measured. The floor of 0.03 GB per cell covers circuits whose cells cost more.
- The replayed synapses are estimated from the share of each source population that spikes, times 2.5 and capped. Source sets chosen for their connections to the simulated cells could replay more.
- Runs much longer than 3 s, and spike inputs much denser than 50 spikes per source, were not measured.
- Skipping the connections that no replay can activate (neurodamus PR 602) would lower the synapse term for runs with little replay; the model would then over-allocate them.

# Circuit extraction: updated resource estimation

Summary of the update of the circuit extraction resource estimation in `app/services/resource_estimation/circuit_extraction.py`. The plots and tables behind it are in [`resource_estimation_updates.ipynb`](resource_estimation_updates.ipynb).

## Benchmarks

175 successful re-extractions from circuit hierarchies across three levels. Root circuits: nbS1 (4.2M biophysical neurons), nbS1-O1 (212k), rCA1 (456k). The runs used `do_virtual=True` and `create_external=True`, and measured per-step time and peak memory. The memory, time and disk allocations of these runs were chosen manually by trial and error; they serve as targets, since they were sufficient (failed runs are not part of the data).

Parent circuit sizes come from the circuit metrics, with afferent and externalized virtual populations kept apart:

| Parent | Biophysical neurons | Virtual neurons (afferent + external) | Synapses (bio + virtual + external) |
| --- | --- | --- | --- |
| nbS1 | 4,234,929 | 471,368 + 0 | 9,138M + 963M + 0 |
| nbS1-O1 | 211,712 | 24,794 + 549,126 | 407M + 49M + 104M |
| nbS1-HEX0 | 30,190 | 8,866 + 270,943 | 41M + 7M + 32M |
| rCA1 | 456,378 | 1,267,238 + 0 | 821M + 9,122M + 0 |
| rCA1 cylinder | 6,213 | 267,238 + 26,985 | 7M + 125M + 4M |

## Findings

- The old formulas scaled memory and time with the number of input neurons. That does not match the data: the split step (reading the parent circuit) and the registration step (writing the extracted one) scale with synapses. Per neuron, the split time differs about 30-fold between parents; per synapse only about 2-fold. rCA1 has fewer neurons than nbS1, but about as many synapses (mostly from virtual neurons), and a similar split time.
- Peak memory grows with the parent's synapses and saturates at about 17 GB for large parents (16–17 GB for 561M to 10G synapses).
- The time is the sum of the split step (about 0.4 h per 1000M input synapses) and the registration step (about 0.01 h per M output synapses).
- Rare runs had a much slower split step, taking 5–7 h in total for nbS1-O1 extractions that typically take 0.2–1.5 h. The cause is still unknown.

## New formulas

Synapses are counted from the circuit metrics; the output is the share of the input that the extracted biophysical neurons account for.

| | Old | New |
| --- | --- | --- |
| Memory (GB) | `1 + 55e-6 * input neurons` | `1.2 * min(24, 2 + 0.04e-6 * input synapses)` |
| Time limit (h) | `ceil(5e-6 * input neurons)` | `ceil(1 + 2 * (0.4e-9 * input synapses + 10.5e-9 * output synapses))` |
| Extra disk (GB) | `1 + 1.85e-7 * output synapses` | `1 + 3.9e-7 * output synapses`, requested in steps of 50 GB |

- Memory: a margin of 1.2 on the fitted parent term, with a cap so that large parents get the 30 GB machine that was used successfully, and an offset of 2 GB for more headroom on small parents.
- Time: the typical case with a margin of 2, plus 1 h, which also covers the worst runs of the small parents. The slow-split outliers of nbS1-O1 are not covered.
- Disk: no measurements of disk usage were available, and the generated assets (compressed circuit, connectivity matrix) also need space. The factor is set on the safe side so that the largest benchmark extraction (nbS1 to 212k neurons) gets the 200 GB it needed, and requests are rounded up to 50, 100, 150 or 200 GB.
- Limits: estimates above the largest machine (120 GB), 24 h, or 200 GB of extra disk are rejected, with the hint to extract fewer neurons or turn off including virtual and/or creating external populations.

## Virtual and external populations

As in brainbuilder, afferent virtual populations are counted with `do_virtual` and externalized ones (`external_*`, from an earlier extraction) with `create_external`. The old formulas counted all virtual populations, external ones included, with `do_virtual`.

## Comparison with the old formulas

- Memory: lower than before for most cases (30 instead of 48–96 GB for nbS1-O1 and rCA1), but above all measured peaks. nbS1 extractions, rejected before (about 260 GB), are now accepted.
- Time: follows the extracted size instead of being constant per parent. Lower than before only for small extractions from large parents, where the benchmarks show the typical run time is short.
- Disk: never lower than before.
- Some large extractions (10–100% of large parents) that were accepted before are now rejected by the stricter disk factor or the 24 h limit.

## Open points

- The model rests on five parents. The ramp of the memory term between 136M and 561M synapses and the saturation above 10G synapses are not covered by measurements.
- No benchmarks without virtual or external populations; their estimates are extrapolated from the same formulas.
- No measured disk usage; the disk factor is a conservative guess.
- The cause of the slow split runs is still to be investigated.

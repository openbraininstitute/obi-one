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
- The task has two parts that run one after the other: (a) the extraction (split step), which reads the parent and scales with the input synapses, and (b) the registration of the extracted circuit, including its validation and the generation of additional assets, which scales with the output synapses.
- Extraction peak memory grows with the parent's synapses and saturates at about 17 GB for large parents (16–17 GB for 561M to 10G synapses). Registration peak memory grows with the output synapses (up to 22 GB for nbS1 to 212k neurons).
- The time is the sum of the extraction (about 0.4 h per 1000M input synapses) and the registration (about 0.01–0.02 h per M output synapses).
- Rare runs had a much slower split step, taking 5–7 h in total for nbS1-O1 extractions that typically take 0.2–1.5 h. The cause is still unknown.

## New formulas

Synapses are counted from the circuit metrics; the output is the share of the input that the extracted biophysical neurons account for.

| | Old | New |
| --- | --- | --- |
| Memory (GB) | `1 + 55e-6 * input neurons` | larger of extraction `1.2 * min(17, 2 + 0.04e-6 * input synapses)` and registration `1.2 * (2 + 0.044e-6 * output synapses)` |
| Time limit (h) | `ceil(5e-6 * input neurons)` | `ceil(1 + 2 * (0.4e-9 * input synapses + 10.5e-9 * output synapses))` |
| Extra disk (GB) | `1 + 1.85e-7 * output synapses` | `1 + 3.9e-7 * output synapses`, requested in steps of 50 GB |

- Memory: a margin of 1.2 on each part, with an offset of 2 GB for more headroom on small circuits. The extraction part saturates for large parents; the registration part covers large extractions (nbS1 to 212k neurons gets the 30 GB machine that was used successfully).
- Time: the typical case of both parts with a margin of 2, plus 1 h, which also covers the worst runs of the small parents. The slow-split outliers of nbS1-O1 are not covered.
- Disk: no measurements of disk usage were available, and the generated assets (compressed circuit, connectivity matrix) also need space. The factor is set on the safe side so that the largest benchmark extraction (nbS1 to 212k neurons) gets the 200 GB it needed, and requests are rounded up to 50, 100, 150 or 200 GB.
- Limits: estimates above the largest machine (120 GB), 24 h, or 200 GB of extra disk are rejected, with the hint to extract fewer neurons or turn off including virtual and/or creating external populations.

## Virtual and external populations

As in brainbuilder, afferent virtual populations are counted with `do_virtual` and externalized ones (`external_*`, from an earlier extraction) with `create_external`. The old formulas counted all virtual populations, external ones included, with `do_virtual`.

## Comparison with the old formulas

- Memory: lower than before for most cases (30 instead of 48–96 GB for nbS1-O1 and rCA1), but above all measured peaks. nbS1 extractions, rejected before (about 260 GB), are now accepted.
- Time: follows the extracted size instead of being constant per parent. Lower than before only for small extractions from large parents, where the benchmarks show the typical run time is short.
- Disk: never lower than before.
- Some large extractions (10–100% of large parents) that were accepted before are now rejected by the stricter disk factor or the 24 h limit.

The two parts are separate functions (`estimate_extraction_resources`, `estimate_registration_resources`), so that the registration part can later be used for the validation and asset-generation jobs of circuit registration, which currently use fixed allocations.

## Open points

- The model rests on five parents. The ramp of the memory term between 136M and 561M synapses and the saturation above 10G synapses are not covered by measurements.
- No benchmarks without virtual or external populations; their estimates are extrapolated from the same formulas.
- No measured disk usage; the disk factor is a conservative guess.
- The benchmarks record validation, upload and asset generation as one step, so the registration part cannot yet be split further. Separate benchmark sections for these would allow it.
- The cause of the slow split runs is still to be investigated.
- Registration memory and time are only measured up to about 730M output synapses. The registration part has no cap, so used on its own (e.g. for future registration jobs) it would reject circuits above about 1G synapses (24 h and 200 GB limits), which excludes root circuits like nbS1 or rCA1 (about 10G synapses).

## Unsupported case: large extraction from nbS1 with midrange connectivity

One additional run extracted 403,634 neurons from nbS1 with midrange connectivity (14,177M synapses), with `do_virtual=True` and `create_external=False`. It succeeded with 16 CPUs, 120 GB, 24 h and 200 GB extra disk, and took 21.8 h (split 3.8 h at 20.4 GB peak, registration 17.6 h at 32.8 GB peak).

The estimator rejects this extraction (41 h, 528 GB disk). This is accepted, as such extractions are rare. The run shows where the formulas are least accurate:

- Without `create_external`, synapses from biophysical neurons outside the extracted set are dropped. The estimate counts all synapses onto the extracted neurons (1,351M), almost twice the actual output (728M).
- Registration time and memory scale more with biophysical than with virtual synapses (about 0.026 vs. 0.012 h per M synapses), which a single rate per synapse does not capture.
- Extraction memory still grows above 10G parent synapses (20.4 GB for 14.2G), beyond the 17 GB saturation of the extraction part.
- 728M output synapses fit within 200 GB of extra disk, so the disk factor of 3.9e-7 GB per synapse is likely too high (at most about 3e-7).

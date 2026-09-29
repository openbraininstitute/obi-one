# Launch-time resource estimation

`app/services/task.py::estimate_task_resources` overrides the static resources of a
task definition before submission to the launch system.

## EModel optimisation

`app/services/resource_estimation/emodel_optimization.py` — the job always runs on
one cluster instance; only `timelimit` is adjusted.

The shared workload model lives in
`obi_one/scientific/tasks/emodel_building/task2_emodel_optimization/estimate.py`
and is also used for the accounting count (estimated core-hours).

```
used_cores = min(CORES_PER_INSTANCE=96, offspring_size)
n_waves    = ceil(offspring_size / used_cores)              # 1 unless offspring > 96
t_eval     = n_protocols * (T_SIM_S_BASE + T_SIM_S_PER_1K_COMPARTMENTS * n_comp/1000)
t_eval     = min(t_eval, optimisation_timeout)              # per-evaluation cap
wall_s     = OVERHEAD_S + (max_ngen + 1) * n_waves * t_eval
timelimit  = max(02:00, wall_s * 1.5)                       # reject if > 24 h
count      = ceil(used_cores * timelimit_h)                 # core-hours
```

- `n_protocols` is counted from the task-1 extracted-features JSON
  (`protocols` dict, else distinct `efeatures` prefixes).
- `n_compartments` is approximated by the SWC point-line count.
- Oversized estimates raise `ApiError(RESOURCE_ESTIMATION_ERROR)`; nothing is
  clamped silently.
- Calibration: the task logs per-seed wall time and peak RSS (see
  `log_peak_rss` in `obi_one/utils/process.py`). Refit `T_SIM_S_*`, `OVERHEAD_S`
  and `CORES_PER_INSTANCE` against real runs.

## Shared helpers

`app/services/resource_estimation/common.py` holds the launch-system machine
limits (`get_required_cpu_memory_combo`, `get_required_extra_storage_space`)
shared by the machine-based estimators.

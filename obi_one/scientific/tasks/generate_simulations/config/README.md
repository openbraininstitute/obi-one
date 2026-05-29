# `generate_simulations/config/` — class layout

Scan-config classes used by `GenerateSimulationTask`. The hierarchy is split
into three layers along two orthogonal axes — **simulator** (`brian2/`,
`neuron/`) and **model kind** (circuit vs. ME-model, in `base/`) — and the
concrete classes compose them via multiple inheritance.

## Layout

```
config/
├── base/
│   ├── base.py        BaseSimulationScanConfig, SimulationSingleConfigMixin
│   ├── circuit.py     CircuitBaseSimulationScanConfig    (adds `circuit` field)
│   └── me_model.py    MEModelBaseSimulationScanConfig    (adds ME-model `circuit`)
├── brian2/
│   ├── brian2_base.py    Brian2SimulationScanConfig      (Brian2 Initialize fields)
│   └── brian2_circuit.py Brian2CircuitSimulationScanConfig + …SingleConfig
└── neuron/
    ├── neuron_base.py                Neuron equivalent of brian2_base
    ├── neuron_circuit.py             CircuitSimulationScanConfig + …SingleConfig
    ├── neuron_me_model.py            MEModelSimulationScanConfig + …SingleConfig
    ├── neuron_me_model_with_synapses.py
    └── neuron_ion_channel_models.py
```

`base/*` knows nothing about a simulator. `brian2/brian2_base.py` and `neuron/neuron_base.py` know nothing
about the model kind. A concrete config picks one of each:

```
                BaseSimulationScanConfig            (base/base.py)
                  /          |          \
   CircuitBase…  MEModelBase…   Brian2…  Neuron…       (split: model | simulator)
            \   /              \  /         |
             \ /                \/          |
  CircuitSimulationScanConfig    Brian2CircuitSimulationScanConfig
  MEModelSimulationScanConfig    (concrete = simulator × model kind)
```

For each concrete `…ScanConfig` there is a `…SingleConfig` that mixes in
`SimulationSingleConfigMixin` and forbids list-valued fields (post scan
expansion).

## MRO refresher

Python uses **C3 linearization** to flatten the inheritance graph into a single
list (the MRO). Attribute lookup walks that list **left-to-right** and stops at
the first class that defines the name. Roughly: *the leftmost / most-derived
class wins*.

For `Brian2CircuitSimulationScanConfig(Brian2SimulationScanConfig, CircuitBaseSimulationScanConfig)`
the MRO is:

```
Brian2CircuitSimulationScanConfig
  → Brian2SimulationScanConfig
  → CircuitBaseSimulationScanConfig
  → BaseSimulationScanConfig
  → InfoScanConfig → ScanConfig → OBIBaseModel → BaseModel → object
```

So `instance.timestep` resolves to the value set in
`Brian2SimulationScanConfig.Initialize` even though
`CircuitBaseSimulationScanConfig` is also in the chain — exactly what you want.

`Initialize` follows the same rule; each concrete class defines its own inner
`Initialize` that inherits from both parents' `Initialize` so the MRO of the
inner class mirrors the outer one.

## ClassVar vs. PrivateAttr — pick ClassVar

For per-class constants (the simulator timestep, a soma marker string, a
default `spike_location`, the schema-extras dict) **always use `ClassVar`, not
Pydantic's `PrivateAttr`**:

```python
class Brian2SimulationScanConfig(BaseSimulationScanConfig, abc.ABC):
    class Initialize(BaseSimulationScanConfig.Initialize):
        timestep: ClassVar[PositiveFloat] = _SIMULATION_TIMESTEP_MILLISECONDS  # good

class NeuronSimulationScanConfig(BaseSimulationScanConfig, abc.ABC):
    class Initialize(BaseSimulationScanConfig.Initialize):
        spike_location: ClassVar[str] = "soma"                                  # good
        timestep: ClassVar[PositiveFloat] = _SIMULATION_TIMESTEP_MILLISECONDS
```

### Why not `PrivateAttr`?

Pydantic stores private attrs in `__private_attributes__`, which is built by
iterating bases and merging — **later bases overwrite earlier ones** in that
dict. With multiple inheritance that resolution order is effectively the
*reverse* of the Python MRO: the right-most parent wins, not the left-most.

Concretely, if `Brian2SimulationScanConfig.Initialize` declared
`_timestep = PrivateAttr(default=BRIAN2_DT)` and
`CircuitBaseSimulationScanConfig.Initialize` declared
`_timestep = PrivateAttr(default=CIRCUIT_DT)`, then for
`Brian2CircuitSimulationScanConfig.Initialize(Brian2…, CircuitBase…)`:

| Lookup mechanism                | Winning class                       | Value      |
| ------------------------------- | ----------------------------------- | ---------- |
| Python MRO (what readers expect)| `Brian2SimulationScanConfig`        | `BRIAN2_DT`|
| Pydantic `__private_attributes__`| `CircuitBaseSimulationScanConfig`  | `CIRCUIT_DT`|

The simulator-specific override silently loses to the model-kind base — the
opposite of the intent, and invisible without inspecting
`__private_attributes__`. Reordering the base list to "fix" it then breaks the
field MRO, so there is no clean escape.

`ClassVar` sidesteps the problem entirely: it is a plain Python class attribute
that obeys MRO, is not part of the Pydantic field/private-attr machinery, and
survives `model_dump` / `model_validate` round-trips (unlike `PrivateAttr`,
which is dropped and has to be re-asserted on each rebuilt instance — see the
`_timestep` re-assertion loop in `examples/J_drosophila_brian2_sonata/`).

### Don't put private state on the config — put it on the Task

Even for runtime/cache-like state, **do not use `PrivateAttr` on a
`ScanConfig` / `SingleConfig` here.** The configs participate in the multiple-
inheritance graph described above, so any `PrivateAttr` declared on them is
subject to the same reverse-MRO resolution bug; on top of that, configs are
routinely round-tripped through `model_dump` / `model_validate` (during scan
expansion, persistence, schema export), which **drops `PrivateAttr` values** —
forcing callers to re-assert them on every rebuilt instance (see the
`_timestep` re-assertion loop in `examples/J_drosophila_brian2_sonata/`).

Runtime state belongs on the `Task` that consumes the config, not on the
config itself. `GenerateSimulationTask` (`../task/task.py`) is the right home
for things like `_sonata_config`, `_circuit`, `_entity_cache`,
`_neuron_set_definitions`, etc. — `Task` subclasses are not part of the config
MRO and are not serialized, so `PrivateAttr` behaves normally there.

Rule of thumb:

- **Constant for a config class, possibly overridden in subclasses** →
  `ClassVar` on the config.
- **Mutable runtime/cache state** → `PrivateAttr` on the **`Task`**, never on
  the config.

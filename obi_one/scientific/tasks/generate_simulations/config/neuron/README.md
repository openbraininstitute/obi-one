# `config/neuron/` — neuron-based simulation scan configs

This directory holds the concrete `*SimulationScanConfig` / `*SimulationSingleConfig`
classes for neuron-based simulation campaigns (circuit, ME-model, ME-model with
synapses, ion-channel model). All inherit from intermediates defined here and from
domain-specific bases in `config/` itself.

## Layered hierarchy

```
SimulationScanConfig          (config/base.py)          abstract base for any simulation
  └── NeuronSimulationScanConfig   (neuron/neuron_base.py)   marker base for neuron-based sims
        └── CircuitSimulationScanConfig          (neuron/neuron_circuit.py)
        └── MEModelSimulationScanConfig          (neuron/neuron_me_model.py)
        └── IonChannelModelSimulationScanConfig  (neuron/neuron_ion_channel_models.py)
        └── MEModelWithSynapsesCircuitSimulationScanConfig
              (neuron/neuron_me_model_with_synapses.py)
              (additionally extends CircuitSimulationScanConfig)

SimulationSingleConfigMixin   (config/base.py)
  └── NeuronSimulationSingleConfig (neuron/neuron_base.py)
        └── <each *SingleConfig> via multiple inheritance with its *ScanConfig
```

`NeuronSimulationScanConfig` and `NeuronSimulationSingleConfig` are deliberately
pass-through right now — they exist as named hooks for future neuron-wide behaviour
(validators, common ClassVars, mass renames) without having to touch every leaf
class.

## Domain "field bundles" live one level up

Field/ClassVar bundles shared by multiple neuron configs live in `config/` (not
under `neuron/`) so they can be reused by non-neuron contexts later. The pattern:

```python
# config/circuit.py
class CircuitSimulationScanConfig(SimulationScanConfig):
    """All circuit-specific fields: neuron_sets, stimuli, distributions, Initialize…"""

# neuron/neuron_circuit.py
class CircuitSimulationScanConfig(CircuitSimulationScanConfig, NeuronSimulationScanConfig):
    """Concrete neuron-based circuit simulation campaign."""
```

`CircuitSimulationScanConfig` is *named* like a standalone scan config (not "Mixin") because
it inherits from `SimulationScanConfig` and is structurally a complete config — it
is just not the one wired up for use. Combining it with `NeuronSimulationScanConfig`
produces the concrete class.

## Single-config pattern

Each `*SingleConfig` uses multiple inheritance to add the
`SimulationSingleConfigMixin` machinery (no-lists enforcement, entity registration)
to its scan-config:

```python
class CircuitSimulationSingleConfig(
    CircuitSimulationScanConfig,
    NeuronSimulationSingleConfig,
):
    """Only allows single values."""
```

MRO walks the scan-config chain first, then the single-config chain, joining at
`SimulationScanConfig` via C3 linearization.

## Why diamond inheritance is fine here

`CircuitSimulationScanConfig(CircuitSimulationScanConfig, NeuronSimulationScanConfig)` is a
diamond — both bases share `SimulationScanConfig` as an ancestor. Python's C3
linearization deduplicates the shared base and visits it exactly once:

```
CircuitSimulationScanConfig
 → CircuitSimulationScanConfig
 → NeuronSimulationScanConfig
 → SimulationScanConfig          ← visited once, after both children
 → InfoScanConfig → ScanConfig → OBIBaseModel → BaseModel → ABC → object
```

Pydantic's metaclass walks this MRO to collect fields. Each ancestor contributes
its own annotated fields, producing the union on the concrete class
(`neuron_sets`, `stimuli`, `distributions` from `CircuitSimulationScanConfig`; `timestamps`,
`recordings` from `SimulationScanConfig`; `info` from `InfoScanConfig`; the
discriminator `type` from `OBIBaseModel`).

## Why `CircuitSimulationScanConfig` inherits from `SimulationScanConfig`, not nothing

It would be tempting to make `CircuitSimulationScanConfig` a plain Python class (a "mixin")
and rely on Pydantic harvesting its annotations through the MRO. That works
functionally, but it triggers shadow warnings whenever a subclass overrides a
field — for example `MEModelWithSynapsesCircuitSimulationScanConfig` re-declaring
`neuron_sets` to specialize its type:

```
UserWarning: Field name "neuron_sets" in "MEModelWithSynapsesCircuitSimulationScanConfig"
shadows an attribute in parent "CircuitSimulationScanConfig"
```

The reason: on a plain class, `neuron_sets = Field(...)` is just a class attribute
holding a `FieldInfo`, not a registered Pydantic field. Pydantic warns because
from its bookkeeping perspective the override is clobbering an unrelated
attribute, not specializing a known field.

Inheriting from `SimulationScanConfig` (so the class is itself a `BaseModel`)
registers `neuron_sets`, `initialize`, etc. as first-class Pydantic fields on
`CircuitSimulationScanConfig`. Subclass overrides are then recognized as field overrides
and the warnings disappear.

## Adding a new neuron-based simulation config

1. If the new config introduces a domain bundle that could ever stand on its own
   (analogue of `CircuitSimulationScanConfig`), put that in `config/<domain>.py`,
   inheriting from `SimulationScanConfig`.
2. In `config/neuron/neuron_<domain>.py`, define:
   - `<Domain>SimulationScanConfig(<DomainScanConfig>, NeuronSimulationScanConfig)`
   - `<Domain>SimulationSingleConfig(<Domain>SimulationScanConfig, NeuronSimulationSingleConfig)`
3. Register the new types in `obi_one/__init__.py`, `unions/unions_scan_configs.py`,
   and `unions/config_task_map.py`.

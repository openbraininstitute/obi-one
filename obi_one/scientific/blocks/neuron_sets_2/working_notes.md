# Parameters of Blocks which are references to other Blocks (of a specific set of types) in a ScanConfig BLOCK_DICTIONARY of a particular set of types

I am a parameter:
- My type derives from BlockReference to signal the type of reference I accept
- I can be resolved into a Block (at this point the BlockReference logic checks that the block_refernce points to block of the allowed types)
- Maybe I want to be a union of BlockReferences
- Extra: I also accept None as a default. My parent Block's logic should specify what to do in this default case.

```python
source_neuron_set: NeuronSet2Reference | None = Field(
  default=None,
  title="Neuron Set (Source)",
  description="Source neuron set to simulate",
  json_schema_extra={
      SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
      SchemaKey.REFERENCE_TYPE: NeuronSet2Reference.__name__,
  },
)

targeted_neuron_set: BiophysicalAndPointNeuronSet2Reference | None = Field(
  default=None,
  title="Neuron Set (Target)",
  description="Target neuron set to simulate",
  json_schema_extra={
      SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
      SchemaKey.REFERENCE_TYPE: BiophysicalAndPointNeuronSet2Reference.__name__,
  },
)
```

# Dictionaries in ScanConfigs

I am a dictionary in a ScanConfig:
- I accept any class in a discrimiated union
- I also specify the types of references I support


```python
neuron_sets: dict[str, AllNeuronSet2Union] = Field(
        default_factory=dict,
        title="Neuron Sets",
        description="Neuron sets for the simulation (new version).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPE: NeuronSet2Reference.__name__,
            SchemaKey.SINGULAR_NAME: "Neuron Set",
            SchemaKey.GROUP: BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    synaptic_manipulations: dict[str, SynapticManipulationsUnion] = Field(
        default_factory=dict,
        description="Synaptic manipulations for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPE: SynapticManipulationsReference.__name__,
            SchemaKey.SINGULAR_NAME: "Synaptic Manipulation",
            SchemaKey.GROUP: BlockGroup.CIRCUIT_MANIPULATIONS_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
```




# Block Union and Block Reference definitions




# What we might want to add
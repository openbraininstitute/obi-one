## block_dictionary

ui_element: `block_dictionary`

- They should contain no `properties`
- They should contain `additionalProperties` with a single `oneOf` array with block schemas.
- They should contain a `singular_name`.
- They should contain a `reference_type`.

Reference schema: [block_dictionary](reference_schemas/block_dictionary.jsonc)

### Example Pydantic implementation

```py
class Config:

    ## SimulationNeuronSetUnion is a union of blocks (i.e. classes with block_elements)

    neuron_sets: dict[str, SimulationNeuronSetUnion] = Field(
        default_factory=dict,
        title="Neuron sets",
        description="Neuron sets for the simulation.",
        json_schema_extra={
            "ui_element": "block_dictionary",
            "group": "Group 1", # Must exit in parent config's `group_order` array
            "group_order": 0, # Unique within the group
            "singular_name": "Neuron Set",
            "reference_type": "NeuronSetReference",
        }
    )

```

### UI design

<img src="designs/block_dictionary.png"  width="300" />
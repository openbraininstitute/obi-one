## block_single

ui_element: `block_single`

- They should contain a single `oneOf` array with block schemas.

Reference schema: [block_single](reference_schemas/block_single.jsonc)

### Example Pydantic implementation

```py
class Config:

    ## SimulationNeuronSetUnion is a union of blocks (i.e. classes with block_elements)

    neuron_set: SimulationNeuronSetUnion = Field(
        ui_element="block_single",
        title="Neuron set",
        description="Neuron set for the simulation.",
        group="Group 1", # Must exist in parent config's `group_order` array
        group_order=0, # Unique within the group
    )

```

### UI design

<img src="designs/block_single.png"  width="500" />

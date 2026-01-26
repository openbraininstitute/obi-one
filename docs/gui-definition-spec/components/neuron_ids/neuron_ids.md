## Neuron ids

ui_element: `neuron_ids`

This element's schema is particularly disordered, we have to keep it for legacy reasons (to avoid breaking changes to the schema). But it shouldn't be used in new configs.

Reference schema [neuron_ids](reference_schemas/neuron_ids.json)

Current pydantic implementation (`ui_element` added) for reference:

```py
class Block:
    neuron_ids: NamedTuple | list[NamedTuple] = Field(ui_element="neuron_ids", min_length=1, title="neuron ids", description="description")

```
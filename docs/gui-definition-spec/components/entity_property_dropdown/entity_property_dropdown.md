## Entity property dropdown

ui_element: `entity_property_dropdown`

- Should accept a single `string` as input.
- Should have an `entity_type` non-validating string.
- Should have a `property` non-validating string.

Reference schema [entity_property_dropdown](reference_schemas/entity_property_dropdown.json)

### Example Pydantic implementation

```py
CircuitNode = Annotated[str, Field(min_length=1)] # Required in the schema
NodeSetType = CircuitNode | list[CircuitNode] # list[] not required

class Block:

    node_set: NodeSetType = Field(
        ui_element="entity_property_dropdown",
        entity_type=EntityType.CIRCUIT,
        property=CircuitPropertyType.NODE_SET,
        title="Node Set",
        description="Name of the node set to use.",
        min_length=1,
    )
    
```

### UI design

<img src="designs/entity_property_dropdown.png"  width="300" />
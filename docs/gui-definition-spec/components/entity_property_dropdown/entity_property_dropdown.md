## Entity property dropdown

ui_element: `entity_property_dropdown`

- Should accept a single `string` as input.
- Should have the following non-validating properties:
    - `property_group` (str): The name of a key for which there is corresponding key specified in the `property_endpoints` dictionary of the parent scan config (see below). This value for this key in the `property_endpoints` dictionary references an endpoint which will return a `property ditionary`. This contains various pieces of data can be used by the UI.
- `property` the name of the key to use from the `property ditionary`. In the case of the `entity_property_dropdown` this should be a list of strings.

Reference schema [entity_property_dropdown](reference_schemas/entity_property_dropdown.json)

### Example Pydantic implementation

```py
CircuitNode = Annotated[str, Field(min_length=1)] # Required in the schema
NodeSetType = CircuitNode | list[CircuitNode] # list[] not required

class Block:

    node_set: NodeSetType = Field(
        title="Node Set",
        description="Name of the node set to use.",
        min_length=1,
        json_schema_extra={
                            "ui_element": "entity_property_dropdown",
                            "property_group": EntityType.CIRCUIT,
                            "property": CircuitPropertyType.NODE_SET,
                            "group": "Group 1", # Must be present in its parent's config `group_order` array,
                            "group_order": 0, # Unique within the group.
                        } 
    )
    
```

### UI design

<img src="designs/entity_property_dropdown.png"  width="300" />
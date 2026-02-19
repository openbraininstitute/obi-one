## block_usability_entity_dependent

A `block` can be optionally greyed out from selection for `block_unions` and `block_dictionaries`, based on the value of a boolean returned in an endpoint.

Firstly, all blocks must have the non-validating boolean parameter: 
- `block_usability_entity_dependent` (This is set as False for all Blocks automatically)

If the value of `block_usability_entity_dependent` is set to `True`, then the following properties must also be specified:
- `block_usability_property_group`: The name of a key for which there is corresponding key specified in the `property_endpoints` dictionary of the parent scan config (see below). The value for this key in the `property_endpoints` dictionary references an endpoint which will return a `property ditionary`. Within this property dictionary there is a dictionary titled `usability`, which contains various boolean values which can be used to optionally display different elements.
- `block_usability_property`: The name of the boolean to use from the `usability` dictionary. If true the block should be useable. If false it should be greyed out and unusable.
- `block_usability_false_message`: The message displayed if the value for the key specified by boolean is false.

Additionally the parent scan config should have the following as a non-validing property:
- `property_endpoints` specifying a dictionary which includes a key matching that specified for `block_usability_property_group`, where the value is a url relative to the base url of the api, such as "/mapped-circuit-properties/{circuit_id}" (see Reference schema).

Reference schemas: 
- [block with block_usability_entity_dependent = True](reference_schemas/block_usability_entity_dependent.jsonc)
- [parent scan config](reference_schemas/block_usability_entity_dependent_parent_scan_config.jsonc)

### Example Pydantic implementation

```py
class EntityDependentBlockExample(Block):
    """Example block description."""

    title: ClassVar[str] = "Example block title"

    json_schema_extra_additions: ClassVar[dict] = {
        "block_usability_entity_dependent": True,
        "block_usability_property_group": MappedPropertiesGroup.CIRCUIT,
        "block_usability_property": CircuitUsability.SHOW_INPUT_RESISTANCE_BASED_STIMULI,
        "block_usability_false_message": "This example block is not available for this circuit.",
    }
```

And the required entry in the parent ScanConfig if `block_usability_entity_dependent` is `True`:
```py
json_schema_extra_additions: ClassVar[dict] = {
    "property_endpoints": {UsabilityGroup.CIRCUIT: "/mapped-circuit-properties/{circuit_id}"},
}
```

### UI design

<!-- <img src="designs/block_dictionary.png"  width="300" /> -->
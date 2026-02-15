## block_usability_entity_dependent

Note a block can be optionally greyed out from selection for block_unions and block_dictionaries, based on the value of a boolean returned in an endpoint.

Reference schema: [block](reference_schemas/block.jsonc)

### Example Pydantic implementation

```py
class ExampleBlock(BLOCK):

    json_schema_extra_additions: ClassVar[dict] = {
        "block_usability_entity_dependent": True,
        "block_usability_entity_type": EntityType.CIRCUIT,
        "block_usability_property": CircuitSimulationUsabilityOption.SHOW_ELECTRIC_FIELD_STIMULI,
        "block_usability_false_message": "This stimulus is currently only supported for microcircuits.",
    }
```

<!-- ### UI design -->

<!-- <img src="designs/block_dictionary.png"  width="300" /> -->
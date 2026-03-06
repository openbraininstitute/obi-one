## Model identifier

ui_element: `model_identifier`

- Should accept as input an object including an `id_str` string field.

Reference schema [model_identifier](reference_schemas/model_identifier.jsonc)

### Example Pydantic implementation

```py

class Circuit:
    pass

# Required
class CircuitFromId(OBIBaseModel):
    id_str: str = Field(description="ID of the entity in string format.")


class Block:
    circuit: Circuit | CircuitFromId = Field( # Other elements in the union other than `CircuitFromId` not required.
            title="Circuit", description="Circuit to simulate.",
            json_schema_extra={"ui_element": "model_identifier"} 
        )
```

### UI design

<img src="designs/model_identifier.png"  width="300" />
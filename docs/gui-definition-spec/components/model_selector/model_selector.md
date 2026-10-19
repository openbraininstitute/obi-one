## Model selector single

ui_element: `model_selector_single`

Picks a single entity to reference. The field is one `FromID` entity reference (an object with an `id_str` string), and the schema declares an `entity_query` telling the frontend which entities to browse.

- The field value is an `{"id_str": ...}` object (a `FromID`), not the full entity.
- `entity_query` must be present and carry a `type` (the entitycore entity type to browse). It may also carry `filters` to narrow the browsable set.

### How it differs from `model_identifier`

Both point at a single entity, but they declare the accepted entity differently:

- [`model_identifier`](../model_identifier/model_identifier.md): the accepted entity is encoded in the field's **type** (a discriminated union such as `Circuit | CircuitFromID`, or a list of them for scans). The frontend reads the union's `type` const to know what to browse. Use it for the `/new` page single or scan selector.
- `model_selector_single`: the field is a plain single `FromID` reference and the accepted entity is declared as **data** via `entity_query.type` (optionally with `filters`). Use it for an inline single-entity selector on the configure page, especially when the same entity type needs server-side filtering (for example only ion channel models that have a conductance).

### Example Pydantic implementation

```py
from entitysdk.types import EntityType

ion_channel_model: IonChannelModelFromID = Field(
    title="Ion channel model",
    description="ID of the model to simulate.",
    json_schema_extra={
        SchemaKey.UI_ELEMENT: UIElement.MODEL_SELECTOR_SINGLE,
        SchemaKey.ENTITY_QUERY: {
            "type": EntityType.ion_channel_model,
            SchemaKey.FILTERS: {"conductance_name__isnull": False},
        },
    },
)
```

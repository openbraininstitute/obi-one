## JSON object

UIElement: `UIElement.JSON_OBJECT`

A free-form object entered as JSON, for arguments passed through to a third-party library, whose keys depend on the method chosen. Where the keys are fixed, use [object](../object/object.md).

Reference schema [json_object](reference_schemas/json_object.jsonc)

### Example Pydantic implementation

```py
class Block:
    clustering_method_kwargs: dict = Field(
        default={},
        title="Clustering method kwargs",
        description="Overrides of the clustering method's arguments, as JSON.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.JSON_OBJECT},
    )
```

### UI design

_UI design to be added._

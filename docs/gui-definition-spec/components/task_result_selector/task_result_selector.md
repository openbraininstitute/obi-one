## Task result selector

ui_element: `task_result_selector`

Selects a `TaskResult` entity produced by an upstream task. The field is an entity reference (a
`TaskResultFromID`, i.e. an `{"id_str": ...}` object).

Unlike [model_selector_single](../model_selector/model_selector.md), this element carries **no**
`entity_query`. Instead it declares the concrete TaskResult subtype as data via the
`task_result_type` key. The frontend uses that subtype to resolve and filter the selectable
results, so an `entity_query` is not needed here.

The element must specify:
- `task_result_type`: the concrete TaskResult subtype to select, given as a value of
  entitysdk's `TaskResultType` enum (e.g. `TaskResultType.efeature_extraction__result`, which
  serializes to `"efeature_extraction__result"`).

### Example Pydantic implementation

```py
class OptimizationInitialize(Block):
    target_efeatures: TaskResultFromID = Field(
        title="Target EFeatures",
        description="Result of the 01_efeature_extraction stage staged as the optimization target.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.TASK_RESULT_SELECTOR,
            SchemaKey.TASK_RESULT_TYPE: TaskResultType.efeature_extraction__result,
        },
    )
```

Which produces:

```jsonc
"target_efeatures": {
  "$ref": "#/components/schemas/TaskResultFromID",
  "ui_element": "task_result_selector",
  "task_result_type": "efeature_extraction__result"
}
```

### Validation

- The field schema must validate an entity-reference object (`{"id_str": ...}`).
- The field must declare a `task_result_type` that is a valid `TaskResultType` value.

### UI design

(To be specified.)

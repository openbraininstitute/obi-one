## Hidden elements

Any element can hidden in the UI by specifying the `ui_hidden = true`. All hidden elements must have a `default`.

### Example

```py
class Block:
    field: str = Field(default="hidden input",  # Default must be present if ui_hidden==True
                        title="title",
                        description="description",
                        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
                                            SchemaKey.UI_HIDDEN: True}
                        )
```

### Root elements

`ui_hidden` may also be applied to a **root element** of a ScanConfig (not only to block
elements). A hidden root element is not rendered in the UI, so it does not need a `ui_element`,
`group`, or `group_order`. As with any hidden element, it must have a `default` because it is
never shown or edited. This is useful for configuration values that are set programmatically and
consumed downstream rather than by the user, such as a contract/version marker.

```py
class ExampleScanConfig(ScanConfig):
    contract_version: Literal["task2-config-v2"] = Field(
        default="task2-config-v2",  # Default must be present if ui_hidden==True
        frozen=True,
        title="Task 2 configuration contract version",
        description="Compatibility version consumed by the launch-system runner.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
```

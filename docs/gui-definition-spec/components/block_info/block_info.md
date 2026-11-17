## block_info

ui_element: `block_info`

The root element holding a campaign's name and description. It is shown and edited as a [block_single](../block_single/block_single.md), with one difference: its properties do not have to be filled in while the config is edited.

- It should contain `properties` in its schema which are _block_elements_.
- Those must include `campaign_name` and `campaign_description`, both `string_input`.
- The schema itself is unchanged: both stay in the block's `required` list, and a config without them is still refused when it is generated.

What the UI does with it:

- Missing or invalid values in this block are not flagged, in the list of blocks or in its form, and do not disable the Generate button.
- When Generate is pressed, the UI shows both values to be filled in or changed, writes them into the block, and then generates. It does not generate until both are filled in.

Reference schema: [block_info](reference_schemas/block_info.jsonc)

### Example Pydantic implementation

```py

class Info(Block):
    campaign_name: str = Field(
        title="Campaign name",
        min_length=1,
        description="Name of the campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
        }
    )
    campaign_description: str = Field(
        title="Campaign description",
        min_length=1,
        description="Description of the campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
        }
    )

class Config:

    info: Info = Field(
        title="Info",
        description="Information about the campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_INFO,
            SchemaKey.GROUP: "Group 1", # Must be present in its parent's config `group_order` array,
            SchemaKey.GROUP_ORDER: 0, # Unique within the group.
        }
    )
```

## block_single

ui_element: `block_single`

block_single UI elements are blocks defined at the root level of a scan config.

They should contain `properties` in its schema which are _block_elements_.

Reference schema: [block_single](reference_schemas/block_single.jsonc)

### Example Pydantic implementation

```py

class Info(Block):
    campaign_name: str = Field(
        ui_element="string_input",
        title="campaign name",
        description="Name of the campaign.")

class Config:

    info: Info = Field(
        ui_element="block_single",
        title="Title",
        description="Description",
        group="Group 1", # Must be present in its parent's config `group_order` array,
        group_order=0, # Unique within the group.
    )
```
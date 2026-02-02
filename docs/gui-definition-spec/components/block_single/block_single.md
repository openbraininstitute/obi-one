## block_single

ui_element: `block_single`

block_single UI elements are blocks defined at the root level of a scan config.

They should contain `properties` in its schema which are _block_elements_.

Reference schema: [block_single](reference_schemas/block_single.jsonc)

### Example Pydantic implementation

```py

class Info(Block):
    campaign_name: str = Field(
        
        title="campaign name",
        description="Name of the campaign."
        json_schema_extra={
            "ui_element": "string_input",
        }        
    )

class Config:

    info: Info = Field(
        title="Title",
        description="Description",
        json_schema_extra={
            "ui_element": "block_single",
            "group": "Group 1", # Must be present in its parent's config `group_order` array,
            "group_order": 0, # Unique within the group.
        }        
    )
```
## String selection

ui_element: `string_selection`

Reference schema: [string_selection](reference_schemas/string_selection.json)

### Example Pydantic implementation

```py
class Block:
    field: Literal["A", "B", "C"] = Field(
        title="Option",
        description="Option description.",
        default="A",
        json_schema_extra={
            "ui_element": "string_selection
        }
    )
```

### UI design

The design for string selection dropdown in the closed position:

<img src="designs/string_selection_closed.png" width="300" />

And in the open position, showing one of the options selected:

<img src="designs/string_selection_open.png" width="300" />


## String selection enhanced

ui_element: `string_selection_enhanced`

Reference schema: [string_selection_enhanced](reference_schemas/string_selection_enhanced.json)

This offers an alternative dropdown style for selecting strings in a dropdown, with additional descriptions and/or latex representations, as well as custom titles. 

Particularly, the following should be included in the `json_extra_schema`:
- At least one of the dictionaries `descriptions_by_key` and `latex_by_key`. 
- `title_by_key`.

When any of these three dictionaries are included, they should have valid string values specified for each enum key.

### Example Pydantic implementation

```py
class Block:
    field: Literal["A", "B", "C"] = Field(
        ui_element="string_selection_enhanced",
        title="Option",
        description="Option description.",
        default="A",
        json_schema_extra={
            "title_by_key": {
                "A": r"A_{Title}",
                "B": r"B_{Title}",
                "C": r"C_{Title}",
            },
            "description_by_key": {
                "A": "Description for option A.",
                "B": "Description for option B.",
                "C": "Description for option C.",
            },
            "latex_by_key": {
                "A": r"A_{latex}",
                "B": r"B_{latex}",
                "C": r"C_{latex}",
            }
        }
        
    )
```

### UI Design

The design for string selection dropdown with descriptions in the closed position:

<img src="designs/string_selection_closed_description.png" width="300" />

And in the open position, showing one of the options selected:

<img src="designs/string_selection_open_description.png" width="300" />

The design for string selection dropdown with descriptions by key in the closed position:

<img src="designs/string_selection_closed_latex.png" width="300" />

And in the open position, showing one of the options selected:

<img src="designs/string_selection_open_latex.png" width="300" />


The design for string selection dropdown with latex by key and descriptions by key in the closed position:

<img src="designs/string_selection_closed_latex_description.png" width="300" />

And in the open position, showing one of the options selected:

<img src="designs/string_selection_open_latex_description.png" width="300" />
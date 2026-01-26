## String selection

ui_element: `string_selection`

<!-- Represents a simple input field. -->
<!-- The type should be `string`. -->

Reference schema: [string_selection](reference_schemas/string_selection.json)

### Example Pydantic implementation

```py
class Block:
    field: Literal["A", "B", "C"] = Field(
        title="Select A, B or C",
        description="Select option A, B or C.",
        default="A",
    )
```

### UI design

The design for string selection dropdown in the closed position:

<img src="designs/string_selection_closed.png" width="300" />

The design for string selection dropdown in the open position, showing one of the options selected:
<img src="designs/string_selection_open.png" width="300" />


## String selection extras

Several additional options are available for the presentation of string_selection elements. These only add to the presentation of the ui_element, and do not change the validatity of inputs. These extras do have implications for the validity of the schema, however. 

## String selection key descriptions

See the section of the [string_selection reference schema](reference_schemas/string_selection.json)

### Example Pydantic implementation

```py
class Block:
    field: Literal["A", "B", "C"] = Field(
        title="Select A, B or C",
        description="Select option A, B or C.",
        default="A",
        descriptions_by_key={'A': 'A is a ...', 
                            'B': 'B is a ...', 
                            'C': 'C is a ...'},
        latex_by_key={'A': 'A is a ...', 
                    'B': 'B is a ...', 
                    'C': 'C is a ...'}
    )
```

### UI Design

The design for string selection dropdown with descriptions in the closed position:

<img src="designs/string_selection_closed_description.png" width="300" />

The design for string selection dropdown with descriptions in the open position:

<img src="designs/string_selection_open_description.png" width="300" />



### Latex

<img src="designs/string_selection_closed_latex.png" width="300" />
<img src="designs/string_selection_open_latex.png" width="300" />

### Latex and description

<img src="designs/string_selection_closed_latex_description.png" width="300" />
<img src="designs/string_selection_open_latex_description.png" width="300" />
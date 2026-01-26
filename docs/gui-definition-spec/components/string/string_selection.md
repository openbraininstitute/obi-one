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

<img src="designs/string_selection_closed.png" width="300" />
<img src="designs/string_selection_open.png" width="300" />



## String selection parameter sweep (Not yet supported)

ui_element: `string_selection_parameter_sweep`

<!-- Represents a simple input field. -->

<!-- The type should be `string`. -->

Reference schema: [string_selection_parameter_sweep](reference_schemas/string_selection_parameter_sweep.json)

### Example Pydantic implementation

```py
class Block:
    field: Literal["A", "B", "C"] | List[Literal["A", "B", "C"]] = Field(
        title="Select A, B or C",
        description="Select option A, B or C.",
        default="A",
        minLength=1
    )
```

### UI design

For the simple string selection, string_selection_parameter_sweep follows the design of string_selection, with the addition of a 

<img src="designs/string_selection_parameter_sweep_closed.png" width="300" />
<img src="designs/string_selection_parameter_sweep_open.png" width="300" />


## String extras

Several additional options are available for the presentation of string_selection and string_selection_parameter_sweep elements. These only enhance the presentation of the ui_element, and do not change the validatity of inputs. These do have implications for the validity of the schema, which are checked during validation of the schema


### Description

<img src="designs/string_selection_closed_latex_description.png.png" width="300" />
<img src="designs/string_selection_open_latex_description.png" width="300" />

### Latex

<img src="designs/string_selection_closed_latex.png" width="300" />
<img src="designs/string_selection_open_latex.png" width="300" />

### Latex and description

<img src="designs/string_selection_closed_description.png" width="300" />
<img src="designs/string_selection_open_description.png" width="300" />

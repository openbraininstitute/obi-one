## Expandable list

ui_element: `expandable_list`

- Should have an element_titles list of strings.
- Should have an elelement_ui_elements list of strings.

Reference schema [expandable_list](reference_schemas/expandable_list.json)

### Example Pydantic implementation


```py

class Block:

    duration_voltage_combinations: list[tuple[NonNegativeFloat | list[NonNegativeFloat], float | list[float]]] = Field(
        title="Duration and voltage combinations for each step",
        description="A list of duration and voltage combinations for each step of the SEClamp stimulus. \
                    Each combination specifies the duration and voltage level of a step input. \
                    The duration is given in milliseconds (ms) and the voltage is given in millivolts (mV).",
        json_schema_extra={
            "ui_element": "expandable_list",
            "element_titles": ["Duration", "Voltage"],
            "elelement_ui_elements": ["float_parameter_sweep", "float_parameter_sweep"],
        },
    )
    
```

### UI design

<img src="designs/expandable_list_tmp.jpg"  width="300" />
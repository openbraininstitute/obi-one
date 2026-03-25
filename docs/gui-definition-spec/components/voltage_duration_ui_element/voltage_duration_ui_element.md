## Voltage duration UI element

ui_element: `voltage_duration_ui_element`

- Should have an subelement_ui_elements list of strings.
- The subelement_ui_elements allowed are int_parameter_sweep and float_parameter_sweep
- Should have an subelement_titles list of strings.
- Should have subelement_units list of strings.

Reference schema [voltage_duration_ui_element](reference_schemas/voltage_duration_ui_element.json)

### Example Pydantic implementation


```py

class Block:

    duration_voltage_combinations: list[tuple[NonNegativeFloat | list[NonNegativeFloat], float | list[float]]] = Field(
        title="Duration and voltage combinations for each step",
        description="A list of duration and voltage combinations for each level of the SEClamp stimulus. \
                    The duration is given in milliseconds (ms) and the voltage is given in millivolts (mV).",
        json_schema_extra={
            "ui_element": "voltage_duration_ui_element",
            "subelement_ui_elements": ["float_parameter_sweep", "float_parameter_sweep"],
            "subelement_titles": ["Duration", "Voltage"],
            "subelement_units": ["ms", "mV"],
        },
    )
    
```

### UI design

<img src="designs/voltage_duration_ui_element.png"  width="300" />
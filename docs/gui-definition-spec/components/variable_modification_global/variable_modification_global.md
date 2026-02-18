# Global Variable Modification Blocks

These UI elements are used to modify RANGE and GLOBAL NEURON NMODL (ion channel mod) file variables at section_list, section and compartment level. See [SONATA documentation](https://sonata-extension.readthedocs.io/en/latest/sonata_simulation.html#parameters-required-for-modifications) for more details. GLOBAL variables are constant across all sections of a neuron. e.g. celsius, v_init and other variables declared as GLOBAL in ion channel mod files.

#### Properties

- `ui_element`: Must be one of `"ion_channel_global_variable_modification"`.
- `title`: Title of the modification block.
- `description`: Description of the modification block.
- `property_group`: Group of the property being modified (e.g., `"Circuit"`).
- `property`: The specific property being modified (e.g., `"IonChannelGlobalVariables"`).

#### Example

```py
modification: ByNeuronModification = Field(
    title="GLOBAL Variable Modification",
    description="Ion channel GLOBAL variable modification.",
    json_schema_extra={
        "ui_element": "ion_channel_global_variable_modification",
        "property_group": "Circuit",
        "property": "IonChannelGlobalVariables",
    },
)
```

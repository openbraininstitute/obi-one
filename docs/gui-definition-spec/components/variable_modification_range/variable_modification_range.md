# Range Variable Modification

These UI elements are used to modify RANGE NEURON NMODL (ion channel mod) file variables at section_list, section and compartment level. See [SONATA documentation](https://sonata-extension.readthedocs.io/en/latest/sonata_simulation.html#parameters-required-for-modifications) for more details. The RANGE variables can vary across different sections of a neuron. e.g. gbar_NaTg, gbar_KTst and other variables declared as RANGE in ion channel mod files.

## Properties

- `ui_element`: Must be `"ion_channel_range_variable_modification"`.
- `title`: Title of the modification block.
- `description`: Description of the modification block.
- `property_group`: Group of the property being modified (e.g., `"Circuit"`).
- `property`: The specific property being modified (e.g., `"IonChannelRangeVariables"`).

## Example

```py
modification: BySectionListModification = Field(
    title="RANGE Variable Modification",
    description="Ion channel RANGE variable modification by section list.",
    json_schema_extra={
        "ui_element": "ion_channel_range_variable_modification",
        "property_group": "Circuit",
        "property": "IonChannelRangeVariables",
    },
)
```
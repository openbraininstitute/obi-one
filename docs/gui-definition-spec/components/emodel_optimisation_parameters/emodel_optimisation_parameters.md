# EModel optimisation parameters

ui_element: `emodel_optimisation_parameters`

A distinct [Root UI element](../../gui-definition.md#types-of-ui-element), alongside
`block_single`, `block_union`, and `block_dictionary`. It is the GUI contract for the Task 2
Mechanisms workflow.

## Custom frontend, not rendered from the schema

Unlike the other root UI elements, this element's UI is **built entirely custom on the frontend
and is NOT rendered from the schema**. Its tabs and layout do not correspond to the schema's
nested structure.

As a consequence:

- The frontend hardcodes how to render this element from its `ui_element` alone; the backend does
  not describe the form via the schema.
- The nested fields (`mechanisms`, `global_parameters`, `base_parameters`,
  `distribution_parameters`, and everything under them) carry **no `ui_element`** and no other
  schema-driven UI metadata (no `step`/`step_order`, `entity_query`, `singular_name`, etc.). The
  frontend already knows what each key maps to.
- Some non-UI structural data may still be present where the frontend needs it (for example the
  section-list `choices` / `availability_by_axon_modifier` / `alias_expansions` on the
  region-keyed fields), but this is data, not a UI contract.
- There is no schema validation of this element's inner structure (the `emodel_optimisation_parameters`
  validator is a no-op).

## Root schema

```text
EModelOptimizationScanConfig
├── emodel_optimisation_parameters: EModelOptimisationParameters   # ui_element: emodel_optimisation_parameters
│   ├── mechanisms: MechanismsBySectionList
│   │   ├── ion_channel_models: tuple[IonChannelModelFromID, ...]
│   │   └── mechanism_regions: dict[SectionListName, tuple[MechanismRegionSelection, ...]]
│   ├── global_parameters
│   ├── base_parameters
│   └── distribution_parameters
└── distance_dependent_distributions: dict[str, CustomDistanceDependentDistribution]
```

`emodel_optimisation_parameters` is a root ScanConfig field using its own registered `ui_element`
(`UIElement.EMODEL_OPTIMISATION_PARAMETERS` in `obi_one/core/schema.py`), following the same
root-element contract (`title`, `description`, `group`, `group_order`) as `block_single`.
`distance_dependent_distributions` remains a separate root field.


## Validation

The self-validation performed by the Python models (not the UI schema) still applies:

- `ion_channel_models` must not contain duplicate EntityCore IDs.
- Region assignments and global parameter sources must reference selected models.
- A model may be assigned to more than one region.
- Section keys use the canonical `SectionListName` catalog.
- Section availability follows the selected axon modifier. With `axon_modifier: "none"`,
  `myelinated` rows are unavailable because staged SWC preflight cannot establish a populated
  runtime myelinated section list.
- Fixed and bounds values use `OptimizationValue`.
- Parameter distributions must be declared by the external `distance_dependent_distributions`
  field or be a standard distribution.

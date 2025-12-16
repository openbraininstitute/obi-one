# OBI-ONE Schema


obi-one specifies a schema for configurations of multi-dimensional parameter scans, with three main types of component (📌):
- 📌 [**ScanConfig**](obi_one/core/scan_config.py)s define configurations for parameter scans of different scientific tasks. E.g. [**CircuitSimulationScanConfig**](obi_one/scientific/simulation/simulations.py)
- 📌 [**Block**](obi_one/core/block.py)s are the main components of ScanConfigs. E.g. 
- 📌 **Variables**

Each of these three component types can be annotated with two types of information:
- ✅ Validation information (which is part of the validation). Validation variables may be included as part of the request body as either required or optional parameters.
- ℹ️ Non validation information. Non-validation annotations contain additional information which are useful

For now, we use the ⚠️ symbol to mark possible places where the schema may need to be updated.

---
---

# 📌 Blocks 
Blocks are a type of class in obi-one.

**📌 type: ClassVar[str]** - The class name of the block (i.e. IDNeuronSet) added automatically by obi-one to the schema of each Block. Should be specified in the request body.

**ℹ️ title: ClassVar[str]** - Display name in UI.

**ℹ️ description: ClassVar[str]** - Description showed in UI, and used by the agent.





---

## Block - Parameter - Simple: 
Ex. 1
```
📌 amplitude: 
    ✅ float | list[float] | FloatRange 
        ℹ️ = Field(default=0.1,
                    description="The injected current. Given in nanoamps.",
                    title="Amplitude",
                    units="nA"
                    )
```

Ex 2.
```
📌 simulation_length: (
    ✅ Annotated[
        NonNegativeFloat,
        Field(
            ge=_MIN_SIMULATION_LENGTH_MILLISECONDS, 
            le=_MAX_SIMULATION_LENGTH_MILLISECONDS
        ),
    ]
    | 
    Annotated[
        list[
            Annotated[
                NonNegativeFloat,
                Field(
                    ge=_MIN_SIMULATION_LENGTH_MILLISECONDS,
                    le=_MAX_SIMULATION_LENGTH_MILLISECONDS,
                ),
            ]
        ],
        Field(min_length=1),
    ]
    ) 
        ℹ️ = Field(
            default=_DEFAULT_SIMULATION_LENGTH_MILLISECONDS,
            title="Duration",
            description="Simulation length in milliseconds (ms).",
            units="ms",
        ) 

```

---

### Block - Parameter - EntityFromID (e.g. CircuitFromID)

```
CircuitDiscriminator = Annotated[Circuit | CircuitFromID, Field(discriminator="type")]

        📌 circuit: 
            ✅ CircuitDiscriminator | list[CircuitDiscriminator] 
                ℹ️ = Field(
                    title="Circuit", 
                    description="Circuit to simulate."
                )
```

---

### Block - Parameter - BlockReference (reference to a Block in a BlockDictionary ):

```
📌 neuron_set: (
    ✅ Annotated[
        NeuronSetReference,
            Field(
                title="Neuron Set", ⚠️
                description="Neuron set to which the stimulus is applied.", ⚠️
                supports_virtual=False,
            ),
    ]
    | None)
        ℹ️ = None
```

BlockReference
```
class BlockReference(OBIBaseModel, abc.ABC):
    block_dict_name: str = Field(default="")
    block_name: str = Field()

    allowed_block_types: [LIST_OF_ALLOWED_BLCOK_TYPES]

```

---

### Block - Parameter - EntityPropertyType (e.g. CircuitPropertyType.NodeSet)

```
📌 node_set: 
    ✅ Annotated[
        NodeSetType, Field(⚠️ min_length=1, entity_property_type=CircuitPropertyType.NODE_SET)
    ]
    ℹ️ = ⚠️
```

where NodeSetType:
```
CircuitNode = Annotated[str, Field(min_length=1)]
NodeSetType = CircuitNode | list[CircuitNode]
```


---

### Block - NamedTuple
```
neuron_ids: NamedTuple | Annotated[list[NamedTuple], Field(min_length=1)]
```

---
---

# Scan Config

**📌 type: ClassVar[str]** - The class name of the ScanConfig (i.e. CircuitSimulationScanConfig) added automatically by obi-one to the schema of each Block. Should be specified in the request body.

**ℹ️ title: ClassVar[str]** - Display name (currently not used).

**ℹ️ description: ClassVar[str]** - Description for coders and AI agent (currently not used in UI).


# ScanConfig - 📌 RootBlock
```
📌 initialize: 
    ✅ Initialize 
        ℹ️ = Field(
            title="Initialization",
            description="Parameters for initializing the simulation.",
            group=BlockGroup.SETUP_BLOCK_GROUP,
            group_order=1,
        )
```

# ScanConfig - 📌 SelectedRootBlock
```
📌 neuron_set: 
    ✅ CircuitExtractionNeuronSetUnion 
        ℹ️ = Field(
            title="Neuron Set",
            description="Set of neurons to be extracted from the parent circuit, including their"
            " connectivity.",
            group=BlockGroup.EXTRACTION_TARGET,
            group_order=0,
        )
```

# ScanConfig - 📌 BlockDictionary
```
📌 timestamps: 
    ✅ dict[str, TimestampsUnion] 
        ℹ️ = Field(
            default_factory=dict,
            title="Timestamps",
            reference_type=TimestampsReference.__name__,
            description="Timestamps for the simulation.",
            singular_name="Timestamps",
            group=BlockGroup.SETUP_BLOCK_GROUP,
            group_order=0,
        )
```

# ScanConfig - ℹ️ <del>block_</del>block_group_order

```
class Config:
    json_schema_extra: ClassVar[dict] = {
        "block_block_group_order": [
            BlockGroup.SETUP_BLOCK_GROUP,
            BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            BlockGroup.CIRUIT_COMPONENTS_BLOCK_GROUP,
            BlockGroup.EVENTS_GROUP,
            BlockGroup.CIRCUIT_MANIPULATIONS_GROUP,
        ],
        ...
    }
```

# ScanConfig - ℹ️ default_block_reference_labels

```
class Config:
    json_schema_extra: ClassVar[dict] = {
        ...

        "default_block_reference_labels": {
            NeuronSetReference.__name__: DEFAULT_NODE_SET_NAME,
            TimestampsReference.__name__: DEFAULT_TIMESTAMPS_NAME,
        },
    }
```
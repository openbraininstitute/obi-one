# Block:
```
“title: ClassVar[str]” (display name in UI)
“description” (Description showed in UI, and currently used by agent)
“type” added automatically
```

---

### Block - Parameter - Simple: 
Ex. 1
```
amplitude: float | list[float] | FloatRange = Field(
        					                    default=0.1,
        					                    description="The injected current. Given in nanoamps.",
                                                title="Amplitude",
                                                units="nA"
                                            )
```

Ex 2.
```
simulation_length: (
                Annotated[
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
            ) = Field(
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

        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
            title="Circuit", description="Circuit to simulate."
        )
```

---

### Block - Parameter - BlockReference (reference to a Block in a BlockDictionary ):


Example use
```
neuron_set: (
        Annotated[
            NeuronSetReference,
            Field(
                title="Neuron Set",
                description="Neuron set to which the stimulus is applied.",
                supports_virtual=False,
            ),
        ]
        | None
    ) = None
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

Ex. 1
```
node_set: Annotated[
        NodeSetType, Field(min_length=1, entity_property_type=CircuitPropertyType.NODE_SET)
    ]
```

---

### Block - NamedTuple
```
neuron_ids: NamedTuple | Annotated[list[NamedTuple], Field(min_length=1)]
```

---

# Scan Config

```
“name”
“description”
“type” added automatically
```


# ScanConfig - RootBlock

# ScanConfig - SelectedRootBlock

# ScanConfig - BlockDictionary
```
timestamps: dict[str, TimestampsUnion] = Field(
        default_factory=dict,
        title="Timestamps",
        reference_type=TimestampsReference.__name__,
        description="Timestamps for the simulation.",
        singular_name="Timestamps",
        group=BlockGroup.SETUP_BLOCK_GROUP,
        group_order=0,
    )
```

# ScanConfig - block_block_group_order

# ScanConfig - default_block_reference_labels
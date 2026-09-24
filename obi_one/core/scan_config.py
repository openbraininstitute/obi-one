import logging
import re
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, get_args, get_origin

import entitysdk
from entitysdk.client import Client
from entitysdk.models import Entity, TaskConfig
from entitysdk.types import (
    ActivityStatus,
    TaskActivityType,
    TaskConfigType,
)
from pydantic import model_validator

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference
from obi_one.core.exception import OBIONEError
from obi_one.core.fill_none_references import (
    BlockDefault,
    fill_none_references_in_config,
    resolve_block_default,
)
from obi_one.core.registry import block_ref_registry, task_registry
from obi_one.core.schema import SchemaKey
from obi_one.core.serialization_constants import SCAN_CONFIG_FILENAME
from obi_one.db_sdk import db_sdk

L = logging.getLogger(__name__)

# A default block can introduce references of its own; this bounds that chain.
_MAX_FILL_PASSES = 10

# The label every default's name carries; the schema advertises the unset field with it, and a
# materialized default is expected to start with it so the resolved name reads as intended.
_DEFAULT_LABEL_PREFIX = "Default: "
# Prepended to a default's schema name when it is materialized into a block dictionary, so the
# resolved block reads distinctly from the "Default: ..." label the schema still advertises for
# the unset field. A collision with a different block stacks an index: "Resolved (1) ...".
_RESOLVED_PREFIX = "Resolved "


def _resolved_default_name(default_name: str, index: int = 0) -> str:
    """The name a materialized default takes in its block dictionary.

    ``index`` 0 gives "Resolved <default_name>"; a positive index gives "Resolved (<index>)
    <default_name>", used to avoid colliding with a different block already under that name.

    Raises:
        OBIONEError: If ``default_name`` does not start with "Default: ". Every default a config
            declares is expected to; a name without it would resolve to a misleading key.
    """
    if not default_name.startswith(_DEFAULT_LABEL_PREFIX):
        msg = (
            f"Cannot resolve a default whose name does not start with "
            f"{_DEFAULT_LABEL_PREFIX!r}: {default_name!r}."
        )
        raise OBIONEError(msg)
    if index:
        return f"Resolved ({index}) {default_name}"
    return f"{_RESOLVED_PREFIX}{default_name}"


def _default_name_of(resolved_name: str) -> str:
    """The "Default: ..." name a "Resolved ..." name was built from.

    Inverts ``_resolved_default_name`` for either form: "Resolved Default: X" and
    "Resolved (n) Default: X" both give back "Default: X", so a provisional name can be
    re-resolved at a different index.
    """
    stripped = resolved_name.removeprefix(_RESOLVED_PREFIX)
    # Drop a leading "(n) " index if present, leaving the bare "Default: ..." name.
    match = re.match(r"^\(\d+\) (Default: .*)$", stripped)
    return match.group(1) if match else stripped


def _blocks_equal(first: object, second: object) -> bool:
    """Whether two blocks are the same block by a full dump comparison."""
    return first.model_dump(mode="json") == second.model_dump(mode="json")  # ty:ignore[unresolved-attribute]


def _stacked_resolved_name(default_name: str, block_dict: dict, block: object) -> str:
    """The "Resolved ..." name ``block`` settles on among what ``block_dict`` already holds.

    Takes the plain name when it is free or held by an equal block (the same default, reloaded
    or filled twice), and otherwise stacks "Resolved (1) ...", "Resolved (2) ..." so a different
    block already there is left in place. Equality is a full dump comparison.
    """
    index = 0
    while True:
        candidate = _resolved_default_name(default_name, index)
        existing = block_dict.get(candidate)
        if existing is None or _blocks_equal(existing, block):
            return candidate
        index += 1


def get_all_annotations(cls: type) -> dict[str, type]:
    """Collect annotations from a class and all its parent classes."""
    annotations = {}
    for base in reversed(cls.__mro__):  # reversed so base class first, then subclasses override
        annotations.update(getattr(base, "__annotations__", {}))
    return annotations


class ScanConfig(OBIBaseModel, extra="forbid"):
    """A ScanConfig is a configuration for single or multi-dimensional parameter scans.

    A ScanConfig is composed of Blocks, which either appear at the root level
    or within dictionaries of Blocks where the dictionary is takes a Union of Block types.
    """

    name: ClassVar[str] = "Add a name class' name variable"
    description: ClassVar[str] = """Add a description to the class' description variable"""

    @staticmethod
    def default_blocks() -> dict[str, BlockDefault]:
        """What each unset tagged field resolves to, keyed by the tag it carries.

        The one thing a config declares about its defaults. Turning these into references and
        publishing them to the schema is done below, so a config says what its defaults are and
        nothing about how they are used. A config that leaves nothing to be inferred returns
        nothing, which is the default. See `obi_one.core.fill_none_references`.
        """
        return {}

    @classmethod
    def default_block_references(cls) -> dict[str, BlockReference]:
        """The declared defaults, resolved into references the fill pass can substitute."""
        return {
            tag: resolve_block_default(block_default)
            for tag, block_default in cls.default_blocks().items()
        }

    def __init_subclass__(cls, **kwargs) -> None:
        """Publish the defaults a config declares, so the UI reads what the fill will do.

        `REFERENCE_TAG_DEFAULTS` is derived from `default_block_references` rather than written
        out beside it, because the two were declared separately and drifted: the schema named
        nine tags while the fill answered seventeen, and nothing said so. Deriving it means a
        config declares its defaults once and the schema cannot disagree with them.
        """
        super().__init_subclass__(**kwargs)

        defaults = cls.default_block_references()
        if not defaults:
            return
        # `json_schema_extra` is typed as a dict, a callable or None; only the dict case can
        # carry this, and OBIBaseModel's model_config always sets one.
        extra = cls.model_config.get("json_schema_extra")
        if not isinstance(extra, dict):
            return
        extra[SchemaKey.REFERENCE_TAG_DEFAULTS] = {  # ty:ignore[invalid-assignment]
            tag: {"name": reference.block_name, "block": reference.block.model_dump(mode="json")}
            for tag, reference in defaults.items()
        }

    def fill_none_references(self) -> None:
        """Give every unset tagged reference its default, and register what was used.

        Called before the scan is serialized, so the configs written to disk and the
        entities registered from them name the blocks that actually produced the result
        rather than recording `None` and leaving it to the code version to say.

        Two phases, because a default is itself a block that can leave references of its own
        unset (a synaptic model adds nine unset distributions) and the config may be a reloaded
        one already carrying earlier-materialized defaults:

        1. Fill loop: repeatedly fill unset fields and park each materialized block in its
           dictionary under a name kept unique by identity, so later passes discover it and fill
           its own references. Names are provisional - a half-filled block cannot be compared.
        2. Reconcile: once the loop settles every block is fully filled, so
           `_reconcile_resolved_defaults` gives each its final name - reusing a plain "Resolved
           Default: ..." name when an equal block is already there, else stacking beside it.
        """
        defaults = self.default_block_references()
        if not defaults:
            return

        used_defaults: list[BlockReference] = []
        settled = False
        for _ in range(_MAX_FILL_PASSES):
            used = fill_none_references_in_config(self, defaults)
            if not self._register_used_defaults(used, used_defaults):
                settled = True
                break

        if not settled:
            msg = (
                "Filling unset block references did not settle: a default block appears to keep "
                "introducing references that are themselves unset."
            )
            raise OBIONEError(msg)

        # Every materialized default is now fully filled, so its dump is stable and two of them
        # can be told apart from one filled twice. Only now can each be given its final name.
        self._reconcile_resolved_defaults(used_defaults)

    def _register_used_defaults(
        self, used: list[BlockReference], used_defaults: list[BlockReference]
    ) -> bool:
        """Put each newly used default into its block dictionary so later passes fill it.

        A default is registered under a "Resolved Default: ..." name rather than the "Default:
        ..." label the schema advertises for the unset field, so that a materialized default
        reads as a distinct, resolved block once the config is reloaded - not as the implicit
        default the field still falls back to. The block goes in under a name kept unique by
        block identity so a materialized default never clobbers a differently-keyed block a
        stored config already carried, and later passes discover it (and fill its own unset
        references) from the dictionary.

        Names are only provisional here: a block still filling in its nested references cannot be
        compared for content, so `_reconcile_resolved_defaults` assigns final names once the fill
        has settled. Records each newly used default in ``used_defaults`` and returns whether any
        was new, which is what tells the caller to look again.
        """
        registered_any = False
        for reference in used:
            if any(reference is seen for seen in used_defaults):
                continue
            used_defaults.append(reference)
            block_dict = getattr(self, reference.block_dict_name)
            name = self._register_by_identity(block_dict, reference)
            reference.block_name = name
            registered_any = True
        return registered_any

    @staticmethod
    def _register_by_identity(block_dict: dict, reference: BlockReference) -> str:
        """Register a default's block under a name unique by identity, returning that name.

        Reuses the name of whatever slot already holds this exact block object (a tag filled
        again), and otherwise takes the first "Resolved ..." name not held by a different block.
        """
        base = reference.block_name
        index = 0
        while True:
            candidate = _resolved_default_name(base, index)
            existing = block_dict.get(candidate)
            if existing is None:
                block_dict[candidate] = reference.block
                return candidate
            if existing is reference.block:
                return candidate
            index += 1

    def _reconcile_resolved_defaults(self, used_defaults: list[BlockReference]) -> None:
        """Give each materialized default its final name now that all are fully filled.

        A default drops onto the plain "Resolved Default: ..." name when nothing else holds it
        or the block already there is equal (the same default, reloaded or filled twice), and
        otherwise stacks "Resolved (1) ...", "Resolved (2) ..." so a block a stored config
        carried - one the user may have edited, or one a since-changed library default filled
        differently - is left untouched and the new default keeps its own values. Every
        reference to a block is repointed together, since they share the one block object.

        Children are named before parents: a parent block embeds its children's names, so its
        equality check only sees a stable dump once those names are final. `used_defaults` lists
        each default in the order it was first needed - a parent before the children it
        introduced - so reversing it names children first.
        """
        # The blocks not materialized this fill (e.g. reloaded from a stored config), keyed by
        # their dictionary: a materialized default must not clobber one, only match or stack
        # beside it. Rebuilt from scratch below so a provisional name never lingers.
        materialized = {id(reference.block) for reference in used_defaults}
        kept: dict[str, dict[str, object]] = {}
        for reference in used_defaults:
            name = reference.block_dict_name
            if name not in kept:
                block_dict = getattr(self, name)
                kept[name] = {
                    key: block for key, block in block_dict.items() if id(block) not in materialized
                }

        for reference in reversed(used_defaults):
            block_dict = kept[reference.block_dict_name]
            base = _default_name_of(reference.block_name)
            final_name = _stacked_resolved_name(base, block_dict, reference.block)
            block_dict[final_name] = reference.block
            reference.block_name = final_name

        for name, block_dict in kept.items():
            getattr(self, name).clear()
            getattr(self, name).update(block_dict)

    _block_mapping: dict = None  # ty:ignore[invalid-assignment]

    _campaign: Entity = None  # ty:ignore[invalid-assignment]

    @property
    def campaign(
        self,
    ) -> entitysdk.models.Entity | None:  # ty:ignore[possibly-missing-submodule]
        return self._campaign

    def input_entities(self, db_client: Client) -> list[Entity]:  # ruff: ignore[no-self-use, unused-method-argument]
        return []

    @property
    def campaign_name(self) -> str:
        msg = "You must define a campaign_name property for your ScanConfig subclass."
        raise NotImplementedError(msg)

    @property
    def campaign_description(self) -> str:
        msg = "You must define a campaign_description property for your ScanConfig subclass."
        raise NotImplementedError(msg)

    @property
    def campaign_task_config_type(self) -> TaskConfigType | None:
        registration = task_registry.get_registration_for_scan_config(type(self))
        return registration.campaign_task_config_type if registration is not None else None

    @property
    def campaign_generation_task_activity_type(self) -> TaskActivityType | None:
        registration = task_registry.get_registration_for_scan_config(type(self))
        return (
            registration.campaign_generation_task_activity_type
            if registration is not None
            else None
        )

    def create_campaign_entity_with_config(
        self,
        output_root: Path,
        multiple_value_parameters_dictionary: dict | None = None,
        db_client: Client = None,  # ty:ignore[invalid-parameter-default]
    ) -> TaskConfig:
        if self.campaign_task_config_type is None:
            msg = "campaign_task_config_type must be defined to create generic campaign TaskConfig."
            raise NotImplementedError(msg)

        self._campaign, _ = db_sdk.register_task_config_with_asset(
            client=db_client,
            name=self.campaign_name,
            description=self.campaign_description,
            task_config_type=self.campaign_task_config_type,
            multiple_value_parameters_dictionary={
                "scan_parameters": multiple_value_parameters_dictionary
            },
            input_entities=self.input_entities(db_client=db_client),  # ty:ignore[invalid-argument-type]
            task_config_file_path=output_root / SCAN_CONFIG_FILENAME,
        )

        return self._campaign

    def create_campaign_generation_entity(
        self, generated: list[TaskConfig], db_client: Client
    ) -> None:
        if self.campaign_generation_task_activity_type is None:
            msg = (
                "campaign_generation_task_activity_type must be defined to create "
                "generic campaign generation TaskActivity."
            )
            raise NotImplementedError(msg)

        time_now = datetime.now(UTC)

        db_sdk.create_generic_activity(
            client=db_client,
            activity_type=self.campaign_generation_task_activity_type,
            used=[self._campaign],
            generated=generated,  # ty:ignore[invalid-argument-type]
            activity_status=ActivityStatus.done,
            start_time=time_now,
            end_time=time_now,
        )

    @classmethod
    def empty_config(cls) -> "ScanConfig":
        # Here you use model_construct or build custom behavior
        return cls.model_construct()

    def validated_config(self) -> "ScanConfig":
        return self.__class__.model_validate(self.model_dump())

    @property
    def block_mapping(self) -> dict:
        """Mapping of block class names to block_dict_name and reference_type."""
        if self._block_mapping is None:
            # Get type annotations of the instance's class
            annotations = get_all_annotations(self.__class__)

            # Initialize an empty mapping
            self._block_mapping = {}

            # Iterate through the ScanConfig's attributes
            for attr_name, attr_value in self.__dict__.items():
                # Get the annotated type of this attribute
                # i.e. dict[str, typing.Annotated[SingleTimestamp | ...)
                annotated_type = annotations.get(attr_name)

                # Check if it's a dictionary of Block instances
                if (
                    isinstance(attr_value, dict)
                    and all(isinstance(v, Block) for v in attr_value.values())
                    and annotated_type is not None
                    and get_origin(annotated_type) is dict
                ):
                    # Check that the attribute has a variable: reference_type
                    field_info = self.__pydantic_fields__[attr_name]
                    if (
                        field_info.json_schema_extra
                        and SchemaKey.REFERENCE_TYPES in field_info.json_schema_extra
                    ):
                        reference_type = field_info.json_schema_extra[SchemaKey.REFERENCE_TYPES]
                    else:
                        msg = (
                            f"Attribute '{attr_name}' does not have a 'reference_type'"
                            " in json_schema_extra."
                        )
                        raise ValueError(msg)

                    # Get the type of the dictionary's values
                    # i.e. typing.Annotated[SingleTimestamp | ...
                    dictionary_value_type = get_args(annotated_type)[1]

                    # Get the value inside the annotation
                    # i.e. SingleTimestamp | ... OR SingleTimestamp
                    inside_annotation_type = get_args(dictionary_value_type)[0]

                    # Create a list of classes inside the annotation
                    # If it's a Union, get all classes inside it
                    # Otherwise, just use the single class
                    if isinstance(inside_annotation_type, types.UnionType):
                        classes = list(get_args(inside_annotation_type))
                    else:
                        classes = [inside_annotation_type]

                    # Iterate through the classes and add them to the mapping
                    for block_class in classes:
                        # If the block class is already in the mapping, raise an error
                        if block_class.__name__ in self._block_mapping:
                            msg = (
                                f"Block class {block_class.__name__} already exists in the mapping."
                                " This suggests that the same block class is used in multiple"
                                " dictionaries."
                            )
                            raise ValueError(msg)

                        # Otherwise initialize a new dictionary for this block class in the mapping
                        self._block_mapping[block_class.__name__] = {
                            "block_dict_name": attr_name,
                            SchemaKey.REFERENCE_TYPES: reference_type,
                        }

        return self._block_mapping

    def fill_block_reference_for_block(self, block: Block) -> None:
        """Fill the block reference with the actual Block object it references."""
        for block_attr_value in block.__dict__.values():
            self._resolve_references_in(block_attr_value)

    def _resolve_references_in(self, value: object) -> None:
        """Recursively resolve BlockReference instances in a value."""
        if isinstance(value, BlockReference):
            self._resolve_block_reference(value)
        elif isinstance(value, (tuple, list)):
            for item in value:
                self._resolve_references_in(item)

    def _resolve_block_reference(self, block_reference: BlockReference) -> None:
        """Resolve a single block reference to its actual Block object."""
        if block_reference.block_dict_name and block_reference.block_name:
            try:
                block_reference.block = self.__dict__[block_reference.block_dict_name][
                    block_reference.block_name
                ]
            except KeyError:
                msg = (
                    f"Block '{block_reference.block_name}' not found in "
                    f"'{block_reference.block_dict_name}'. `block_dict_name` must "
                    f"correspond to the name of the root level dictionary which contains "
                    f"the block you are referencing, or should be an empty string to "
                    f"reference a root level block."
                )
                # ValueError, not KeyError: only ValueError/AssertionError are folded into a
                # ValidationError by the model validator this runs inside.
                raise ValueError(msg) from None

        elif not block_reference.block_dict_name and block_reference.block_name:
            # If the block_dict_name is empty, we assume the block_name
            # is a direct reference to a Block instance
            if block_reference.block_name == "neuron_set_extra":
                block_reference.block = self.__dict__[block_reference.block_name]
        else:
            msg = "BlockReference must have a non-empty block_dict_name and block_name."
            raise ValueError(msg)

    @model_validator(mode="after")
    def fill_block_references_and_names(self) -> "ScanConfig":
        for attr_value in self.__dict__.values():
            # Check if the attribute is a dictionary of Block instances
            if isinstance(attr_value, dict) and all(
                isinstance(dict_val, Block) for dict_val in attr_value.values()
            ):
                category_blocks_dict = attr_value

                # If so iterate through the dictionary's Block instances
                for key, block in category_blocks_dict.items():
                    self.fill_block_reference_for_block(block)
                    block.set_block_name(key)

            elif isinstance(attr_value, Block):
                block = attr_value
                self.fill_block_reference_for_block(block)

        return self

    @property
    def single_config_class(self) -> type[OBIBaseModel]:
        """The SingleConfig class this ScanConfig expands into, from TASK_MAP."""
        registration = task_registry.get_registration_for_scan_config(type(self))
        if registration is None:
            msg = (
                f"'{type(self).__name__}' has no entry in TASK_MAP, so the SingleConfig "
                "class it expands into cannot be resolved."
            )
            raise OBIONEError(msg)
        return registration.single_config_cls

    def cast_to_single_coord(self) -> OBIBaseModel:
        """Cast the form to a single coordinate object."""
        class_to_cast_to = self.single_config_class
        single_coord = class_to_cast_to.model_construct(**self.__dict__)
        single_coord.type = class_to_cast_to.__name__
        return single_coord

    @property
    def single_coord_scan_default_subpath(self) -> str:
        return self.single_config_class.__name__ + "/"

    def add(self, block: Block, name: str = "") -> None:
        block_dict_name = self.block_mapping[block.__class__.__name__]["block_dict_name"]
        reference_type_names = self.block_mapping[block.__class__.__name__][
            SchemaKey.REFERENCE_TYPES
        ]

        if name in self.__dict__.get(block_dict_name):  # ty:ignore[unsupported-operator]
            msg = f"Block with name '{name}' already exists in '{block_dict_name}'!"
            raise OBIONEError(msg)

        # Find the reference type that accepts this block class
        block_class_name = block.__class__.__name__
        reference_type = None
        for ref_name in reference_type_names:
            ref_cls = block_ref_registry.get_by_name(ref_name)
            if ref_cls is None:
                continue
            extras = getattr(ref_cls, "json_schema_extra_additions", None)
            if extras is None:
                # No restrictions — accept any block
                reference_type = ref_cls
                break
            allowed = extras.get("allowed_block_types", [])
            if not allowed or block_class_name in allowed:
                reference_type = ref_cls
                break

        if reference_type is None:
            msg = (
                f"No reference type from {reference_type_names}"
                f" accepts block class '{block_class_name}'."
            )
            raise OBIONEError(msg)

        ref = reference_type(block_dict_name=block_dict_name, block_name=name)
        block.set_ref(ref)
        block.set_block_name(name)
        self.__dict__[block_dict_name][name] = block

    def set(self, block: Block, name: str = "") -> None:
        """Sets a block in the form."""
        self.__dict__[name] = block

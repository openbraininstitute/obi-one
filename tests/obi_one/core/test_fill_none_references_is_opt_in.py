"""The fill pass runs for every config, so it has to do nothing to the ones that never asked.

`ScanGenerationTask.execute` calls `fill_none_references` on whatever config it was given,
before serializing it. Two independent things keep that inert for configs that have not opted
in, and this pins both: they declare no defaults, and nothing they hold carries a tag.
"""

import json

import pytest

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey
from obi_one.scientific.tasks.synapse_parameterization.config import (
    SynapseParameterizationScanConfig,
)

OPTED_IN = "SynapseParameterizationScanConfig"


def _subclasses(cls):
    for subclass in cls.__subclasses__():
        yield subclass
        yield from _subclasses(subclass)


def _config_classes():
    return sorted(set(_subclasses(ScanConfig)), key=lambda c: c.__name__)


def _opted_in(config_class):
    return issubclass(config_class, SynapseParameterizationScanConfig)


def test_there_are_configs_to_check():
    # Guards the two tests below against passing because the walk found nothing.
    assert len(_config_classes()) > 10


def test_only_the_synapse_parameterization_config_declares_defaults():
    declaring = [c.__name__ for c in _config_classes() if c.default_block_references()]

    assert all(_opted_in(c) for c in _config_classes() if c.__name__ in declaring)
    assert OPTED_IN in declaring


def test_every_other_config_declares_nothing():
    # The pass returns immediately on an empty mapping, so this is the first of the two gates.
    for config_class in _config_classes():
        if _opted_in(config_class):
            continue
        assert config_class.default_block_references() == {}, config_class.__name__


def test_only_the_tsodyks_markram_blocks_carry_tags():
    # The second gate: even if the pass ran on another config, it only touches fields that
    # declare a role, and nothing outside these blocks does.
    tagged = {
        block_class.__name__
        for block_class in _subclasses(Block)
        for field in block_class.model_fields.values()
        if isinstance(field.json_schema_extra, dict)
        and SchemaKey.REFERENCE_TAG in field.json_schema_extra
    }

    assert tagged == {
        "TsodyksMarkramSynapticModel",
        "ExcitatoryTsodyksMarkramSynapticModel",
        "InhibitoryTsodyksMarkramSynapticModel",
    }


@pytest.mark.parametrize(
    "config_class",
    [c for c in _config_classes() if not _opted_in(c)][:12],
    ids=lambda c: c.__name__,
)
def test_filling_a_config_that_never_opted_in_changes_nothing(config_class):
    try:
        config = config_class.empty_config()
    except Exception:  # ruff: ignore[blind-except]
        # Some configs need arguments to build; this test is about the ones that do not.
        pytest.skip(f"{config_class.__name__} cannot be built without arguments")

    before = json.loads(config.model_dump_json())
    config.fill_none_references()

    assert json.loads(config.model_dump_json()) == before

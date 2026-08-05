import pytest

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.path import NamedPath
from obi_one.core.scan_config import ScanConfig, get_all_annotations
from obi_one.scientific.tasks.folder_compression import (
    FolderCompressionScanConfig,
    FolderCompressionSingleConfig,
)
from obi_one.scientific.tasks.schema_example import SchemaExampleScanConfig


class TestGetAllAnnotations:
    def test_basic_class(self):
        class A:
            x: int
            y: str

        annotations = get_all_annotations(A)
        assert "x" in annotations
        assert "y" in annotations

    def test_inheritance(self):
        class Base:
            x: int

        class Child(Base):
            y: str

        annotations = get_all_annotations(Child)
        assert "x" in annotations
        assert "y" in annotations

    def test_override(self):
        class Base:
            x: int

        class Child(Base):
            x: str

        annotations = get_all_annotations(Child)
        assert annotations["x"] is str


class TestScanConfigClassVars:
    def test_default_name(self):
        assert ScanConfig.name == "Add a name class' name variable"

    def test_default_description(self):
        assert "Add a description" in ScanConfig.description

    def test_folder_compression_name(self):
        assert FolderCompressionScanConfig.name == "Folder Compression"


class TestSingleConfigClass:
    """The SingleConfig a ScanConfig expands into is resolved from TASK_MAP."""

    def test_resolved_from_task_map(self):
        config = FolderCompressionScanConfig(
            initialize=FolderCompressionScanConfig.Initialize(
                folder_path=NamedPath(name="t", path="/t"),
            )
        )
        assert config.single_config_class is FolderCompressionSingleConfig

    def test_unregistered_scan_config_raises(self):
        """SchemaExampleScanConfig is deliberately absent from TASK_MAP."""
        with pytest.raises(OBIONEError, match="no entry in TASK_MAP"):
            _ = SchemaExampleScanConfig.model_construct().single_config_class


class TestScanConfigCreation:
    def test_folder_compression_creation(self):
        config = FolderCompressionScanConfig(
            initialize=FolderCompressionScanConfig.Initialize(
                folder_path=NamedPath(name="test", path="/data/test"),
            )
        )
        assert config.initialize.folder_path.name == "test"
        assert config.initialize.file_format == "gz"
        assert config.initialize.file_name == "compressed"

    def test_with_custom_file_format(self):
        config = FolderCompressionScanConfig(
            initialize=FolderCompressionScanConfig.Initialize(
                folder_path=NamedPath(name="t", path="/t"),
                file_format="bz2",
            )
        )
        assert config.initialize.file_format == "bz2"


class TestEmptyConfig:
    def test_empty_config_returns_instance(self):
        config = FolderCompressionScanConfig.empty_config()
        assert isinstance(config, FolderCompressionScanConfig)


class TestValidatedConfig:
    def test_validated_config_returns_same_type(self):
        config = FolderCompressionScanConfig(
            initialize=FolderCompressionScanConfig.Initialize(
                folder_path=NamedPath(name="t", path="/t"),
            )
        )
        validated = config.validated_config()
        assert isinstance(validated, FolderCompressionScanConfig)
        assert validated.initialize.folder_path.name == "t"


class TestSingleCoordScanDefaultSubpath:
    def test_subpath(self):
        config = FolderCompressionScanConfig(
            initialize=FolderCompressionScanConfig.Initialize(
                folder_path=NamedPath(name="t", path="/t"),
            )
        )
        assert config.single_coord_scan_default_subpath == "FolderCompressionSingleConfig/"


class TestBlockMapping:
    def test_no_dict_blocks_empty_mapping(self):
        config = FolderCompressionScanConfig(
            initialize=FolderCompressionScanConfig.Initialize(
                folder_path=NamedPath(name="t", path="/t"),
            )
        )
        # FolderCompressionScanConfig has no dict block fields
        assert config.block_mapping == {}

    def test_block_mapping_cached(self):
        config = FolderCompressionScanConfig(
            initialize=FolderCompressionScanConfig.Initialize(
                folder_path=NamedPath(name="t", path="/t"),
            )
        )
        mapping1 = config.block_mapping
        mapping2 = config.block_mapping
        assert mapping1 is mapping2


class TestFillBlockReferencesAndNames:
    def test_block_names_set_on_validation(self):
        """ScanConfig model_validator sets block names for dict blocks."""
        # FolderCompressionScanConfig doesn't have dict blocks, but the
        # validator should still run without error
        config = FolderCompressionScanConfig(
            initialize=FolderCompressionScanConfig.Initialize(
                folder_path=NamedPath(name="t", path="/t"),
            )
        )
        assert isinstance(config.initialize, Block)


class TestSetMethod:
    def test_set_block(self):
        config = FolderCompressionScanConfig(
            initialize=FolderCompressionScanConfig.Initialize(
                folder_path=NamedPath(name="t", path="/t"),
            )
        )
        new_init = FolderCompressionScanConfig.Initialize(
            folder_path=NamedPath(name="new", path="/new"),
        )
        config.set(new_init, name="initialize")
        assert config.initialize.folder_path.name == "new"


class TestScanConfigSerialization:
    def test_model_dump(self):
        config = FolderCompressionScanConfig(
            initialize=FolderCompressionScanConfig.Initialize(
                folder_path=NamedPath(name="t", path="/t"),
            )
        )
        dump = config.model_dump()
        assert dump["type"] == "FolderCompressionScanConfig"
        assert "initialize" in dump
        assert dump["initialize"]["folder_path"]["name"] == "t"

    def test_model_dump_json_round_trip(self):
        config = FolderCompressionScanConfig(
            initialize=FolderCompressionScanConfig.Initialize(
                folder_path=NamedPath(name="t", path="/t"),
                file_format="bz2",
            )
        )
        json_str = config.model_dump_json()
        restored = FolderCompressionScanConfig.model_validate_json(json_str)
        assert restored.initialize.file_format == "bz2"

    def test_scan_config_with_list_params(self):
        config = FolderCompressionScanConfig(
            initialize=FolderCompressionScanConfig.Initialize(
                folder_path=NamedPath(name="t", path="/t"),
                file_format=["gz", "bz2"],
            )
        )
        assert config.initialize.file_format == ["gz", "bz2"]

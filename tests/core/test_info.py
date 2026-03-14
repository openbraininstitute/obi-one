import pytest
from pydantic import ValidationError

from obi_one.core.block import Block
from obi_one.core.info import Info


class TestInfo:
    def test_creation(self):
        info = Info(campaign_name="My Campaign", campaign_description="A test campaign")
        assert info.campaign_name == "My Campaign"
        assert info.campaign_description == "A test campaign"

    def test_is_block(self):
        assert issubclass(Info, Block)

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError):
            Info(campaign_name="", campaign_description="desc")

    def test_empty_description_raises(self):
        with pytest.raises(ValidationError):
            Info(campaign_name="name", campaign_description="")

    def test_type_field(self):
        info = Info(campaign_name="test", campaign_description="test desc")
        assert info.type == "Info"

    def test_json_schema_extra_on_fields(self):
        fields = Info.model_fields
        assert fields["campaign_name"].json_schema_extra == {"ui_element": "string_input"}
        assert fields["campaign_description"].json_schema_extra == {"ui_element": "string_input"}

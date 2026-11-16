import pytest

from obi_one.scientific.blocks.timestamps.single import SingleTimestamp
from obi_one.scientific.unions_and_references.timestamps import (
    resolve_timestamps_ref_to_timestamps_block,
)


class TestResolveTimestampsRef:
    def test_falls_back_to_default(self):
        default = SingleTimestamp(start_time=5.0)
        assert resolve_timestamps_ref_to_timestamps_block(None, default) is default

    def test_raises_without_reference_or_default(self):
        with pytest.raises(ValueError, match="default timestamps block must be set"):
            resolve_timestamps_ref_to_timestamps_block(None, None)

from obi_one.scientific.shared_cache import SharedCache


class TestSharedCache:
    def test_creates_mechanisms_subdir(self, tmp_path):
        cache = SharedCache(tmp_path)

        assert cache.mechanisms_dir == tmp_path / "mechanisms"
        assert cache.mechanisms_dir.is_dir()
        assert not hasattr(cache, "prefix")
        assert not hasattr(cache, "root")

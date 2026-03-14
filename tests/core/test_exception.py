import pytest

from obi_one.core.exception import (
    ConfigValidationError,
    OBIONEError,
    ProtocolNotFoundError,
)


class TestOBIONEError:
    def test_creation(self):
        err = OBIONEError("something went wrong")
        assert str(err) == "something went wrong"

    def test_is_exception(self):
        assert issubclass(OBIONEError, Exception)

    def test_raise_and_catch(self):
        msg = "test error"
        with pytest.raises(OBIONEError, match=msg):
            raise OBIONEError(msg)


class TestConfigValidationError:
    def test_is_obi_one_error(self):
        assert issubclass(ConfigValidationError, OBIONEError)

    def test_creation(self):
        err = ConfigValidationError("invalid config")
        assert str(err) == "invalid config"

    def test_catchable_as_obi_one_error(self):
        msg = "bad config"
        with pytest.raises(OBIONEError):
            raise ConfigValidationError(msg)


class TestProtocolNotFoundError:
    def test_creation(self):
        err = ProtocolNotFoundError(["protocol_1", "protocol_2"])
        assert err.args[0] == ["protocol_1", "protocol_2"]

    def test_is_exception(self):
        assert issubclass(ProtocolNotFoundError, Exception)

    def test_not_obi_one_error(self):
        assert not issubclass(ProtocolNotFoundError, OBIONEError)

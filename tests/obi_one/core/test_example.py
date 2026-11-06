from pydantic import BaseModel

from obi_one.core import base


def test_base_model():
    assert issubclass(base.OBIBaseModel, BaseModel)

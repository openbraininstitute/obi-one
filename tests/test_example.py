from fastapi import FastAPI
from pydantic import BaseModel

from app.application import app
from obi_one.core import base


def test_app():
    assert isinstance(app, FastAPI)


def test_base_model():
    assert issubclass(base.OBIBaseModel, BaseModel)

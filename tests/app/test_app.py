from fastapi import FastAPI

from app.application import app


def test_app():
    assert isinstance(app, FastAPI)

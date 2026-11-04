"""Tests for parametric multi-value endpoint error handling."""

import pytest
from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError

from app.endpoints import multi_values as test_module


class TestProcessValueValidationErrors:
    def test_unrecognized_error_type_is_reraised(self):
        """Unknown ValidationError types must not be swallowed as HTTP 400."""

        class Model(BaseModel):
            x: int

        with pytest.raises(ValidationError) as exc_info:
            Model(x="not-an-int")
        original = exc_info.value

        with pytest.raises(ValidationError) as reraised:
            test_module.process_value_validation_errors(original)

        assert reraised.value is original

    def test_known_constraint_error_becomes_http_400(self):
        """Recognized constraint failures still map to client errors."""

        class GtModel(BaseModel):
            x: int = Field(gt=5)

        with pytest.raises(ValidationError) as constraint_exc:
            GtModel(x=1)

        with pytest.raises(HTTPException) as http_exc:
            test_module.process_value_validation_errors(constraint_exc.value)

        assert http_exc.value.status_code == 400
        assert "All values must be >" in http_exc.value.detail

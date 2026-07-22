"""Schemas for the publication endpoints."""

import re

from pydantic import BaseModel, field_validator

DOI_REGEX = re.compile(r"^10.\d{4,9}/[-._;()/:A-Z0-9]+$", re.IGNORECASE)


class PublicationRegisterRequest(BaseModel):
    """Request body for registering a publication by DOI."""

    DOI: str

    @field_validator("DOI", mode="before")
    @classmethod
    def validate_doi(cls, value: str) -> str:
        """Validate that the provided string is a valid DOI."""
        if not DOI_REGEX.match(value):
            msg = f"Invalid DOI format: {value}"
            raise ValueError(msg)
        return value

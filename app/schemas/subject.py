"""Schemas for the subject registration endpoint."""

import re
from datetime import timedelta
from typing import Self
from uuid import UUID

from entitysdk.types import AgePeriod, Sex
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Blocklist: whole-word matches only (case-insensitive) to avoid false positives like "testes"
_BLOCKLIST_WORDS = {"test", "tmp", "todo", "placeholder", "example", "foo", "bar", "asdf", "xxx"}
_BLOCKLIST_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in _BLOCKLIST_WORDS) + r")\b",
    re.IGNORECASE,
)

# Multi-word blocked phrases (case-insensitive substring match)
_BLOCKED_PHRASES = ["delete me", "testing 123"]

_MIN_NAME_LENGTH = 3
_MIN_DESCRIPTION_LENGTH = 10


def _normalize_whitespace(value: str) -> str:
    """Strip and collapse internal whitespace."""
    return " ".join(value.split())


def _check_blocklist(value: str, field_label: str) -> None:
    """Raise ValueError if the value contains blocked words or phrases."""
    if _BLOCKLIST_PATTERN.search(value):
        msg = f"{field_label} contains a disallowed word"
        raise ValueError(msg)
    for phrase in _BLOCKED_PHRASES:
        if phrase.lower() in value.lower():
            msg = f"{field_label} contains a disallowed phrase: '{phrase}'"
            raise ValueError(msg)


def normalize_name(name: str) -> str:
    """Normalize a name for duplicate name comparison.

    Strips all non-alphanumeric characters (spaces, hyphens, underscores, etc.)
    and lowercases the result so that e.g. "Average Rat", "average rat",
    "AverageRat", "Average-rat", "Average_rat" all produce the same key.
    """
    return re.sub(r"[^a-z0-9]", "", name.lower())


def split_name(name: str) -> list[str]:
    return re.split(r"[^a-z0-9]+", name.lower())


class SubjectRegisterRequest(BaseModel):
    """Request body for registering a new subject."""

    model_config = ConfigDict(from_attributes=True, ser_json_timedelta="float")

    name: str = Field(description="Unique name for the subject")
    description: str = Field(description="Description of the subject")
    species_id: UUID = Field(description="ID of the species entity")
    strain_id: UUID | None = Field(default=None, description="ID of the strain entity (optional)")
    sex: Sex = Field(description="Sex of the subject (male or female)")
    weight: float | None = Field(default=None, description="Weight in grams", gt=0.0)
    age_value: timedelta = Field(..., description="Age value interval", gt=timedelta(0))
    age_period: AgePeriod | None = Field(
        default=None, description="Age period (prenatal or postnatal)"
    )

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Normalize and validate the subject name."""
        value = _normalize_whitespace(value)

        if len(value) < _MIN_NAME_LENGTH:
            msg = f"Name must be at least {_MIN_NAME_LENGTH} characters"
            raise ValueError(msg)

        if value.isdigit():
            msg = "Name cannot be purely numeric"
            raise ValueError(msg)

        _check_blocklist(value, "Name")
        return value

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: str) -> str:
        """Normalize and validate the subject description."""
        value = _normalize_whitespace(value)

        if len(value) < _MIN_DESCRIPTION_LENGTH:
            msg = f"Description must be at least {_MIN_DESCRIPTION_LENGTH} characters"
            raise ValueError(msg)

        _check_blocklist(value, "Description")
        return value

    @model_validator(mode="after")
    def age_period_mandatory_with_age_value(self) -> Self:
        """Age period must be provided together with age_value."""
        if not self.age_period:
            msg = "age_period must be provided when age_value is provided"
            raise ValueError(msg)
        return self

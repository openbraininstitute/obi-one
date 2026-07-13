"""Schemas for the subject registration endpoint."""

import re
from datetime import timedelta
from typing import Self
from uuid import UUID

from entitysdk.types import AgePeriod, Sex
from pydantic import BaseModel, Field, field_validator, model_validator

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


def normalize_name_for_comparison(name: str) -> str:
    """Normalize a name for duplicate name comparison.

    Strips all non-alphanumeric characters (spaces, hyphens, underscores, etc.)
    and lowercases the result so that e.g. "Average Rat", "average rat",
    "AverageRat", "Average-rat", "Average_rat" all produce the same key.
    """
    return re.sub(r"[^a-z0-9]", "", name.lower())


class SubjectRegisterRequest(BaseModel):
    """Request body for registering a new subject."""

    name: str = Field(description="Unique name for the subject")
    description: str = Field(description="Description of the subject")
    species_id: UUID = Field(description="ID of the species entity")
    strain_id: UUID | None = Field(default=None, description="ID of the strain entity (optional)")
    sex: Sex = Field(description="Sex of the subject (male or female)")
    weight: float | None = Field(default=None, description="Weight in grams", gt=0.0)
    age_value: timedelta | None = Field(
        default=None, description="Age value interval", gt=timedelta(0)
    )
    age_min: timedelta | None = Field(
        default=None, description="Minimum age range", gt=timedelta(0)
    )
    age_max: timedelta | None = Field(
        default=None, description="Maximum age range", gt=timedelta(0)
    )
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
    def age_period_mandatory_with_age_fields(self) -> Self:
        """Age period must be provided when age fields are provided."""
        if any([self.age_value, self.age_min, self.age_max]) and not self.age_period:
            msg = "age_period must be provided when age fields are provided"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def either_age_value_or_age_range(self) -> Self:
        """Either a single age value or an age range can be provided, but not both."""
        if self.age_value and any([self.age_min, self.age_max]):
            msg = "age_value and age_min/age_max cannot both be provided"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def min_max_age_range_consistency(self) -> Self:
        """Age min and max must be provided together or not at all."""
        if self.age_min and self.age_max:
            if self.age_min >= self.age_max:
                msg = "age_max must be greater than age_min"
                raise ValueError(msg)
            return self

        if self.age_min or self.age_max:
            msg = "age_min and age_max must be provided together"
            raise ValueError(msg)

        return self

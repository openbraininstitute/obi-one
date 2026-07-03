"""Schemas for the subject registration endpoint."""

from datetime import timedelta
from typing import Self
from uuid import UUID

from entitysdk.types import AgePeriod, Sex
from pydantic import BaseModel, Field, model_validator


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

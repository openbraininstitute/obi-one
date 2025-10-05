import abc
from typing import Annotated

from pydantic import BaseModel, Field


class Validation(BaseModel, abc.ABC):
    """Base class for validation objects.

    This class is used to define the structure of validation objects.
    It can be extended to create specific validation types.
    """


class SingleValidationOutput(BaseModel, abc.ABC):
    """Base class for single validation output objects.

    This class is used to define the base structure of validation output objects.
    """

    name: Annotated[
        str,
        Field(
            title="Validation Name",
            description="Name of the validation.",
            examples="Simulatable Neuron Depolarization Block Validation",
        ),
    ]
    passed: Annotated[
        bool,
        Field(
            title="Validation Passed",
            description="Indicates whether the validation passed or not.",
            examples=True,
        ),
    ]
    validation_details: Annotated[
        str,
        Field(
            title="Validation Details",
            description=(
                "Details about the validation, including any errors or warnings. "
                "It will be registgered as an asset on entitycore."
            ),
            examples="Validation passed: No depolarization block detected..",
        ),
    ] = ""
    assets: Annotated[
        list[str],
        Field(
            title="Asset file paths",
            description=(
                "List of paths to the files to be registered as assets of the validation output."
            ),
            examples=["./MEM__1372346-C060114A5__cADpyr_L5_TPCA/depolarization_block_test.pdf"],
        ),
    ] = []

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleCoordMixin

from pydantic import Field

from typing import ClassVar

class Kilosort4ScanConfig(ScanConfig):
    """ScanConfig for extracting sub-circuits from larger circuits."""

    single_coord_class_name: ClassVar[str] = "Kilosort4SingleConfig"
    name: ClassVar[str] = "Kilosort4"
    description: ClassVar[str] = (
        "Kilosort4"
    )

    class Initialize(Block):

        number_of_channels: int | list[int] = Field(
            default=True,
            name="Total number of channels in the binary file, which may be different \
                from the number of channels containing ephys data. The value of this \
                parameter *must* be specified by the user, or `run_kilosort` will \
                raise a ValueError.",
            description="",
        )

        sampling_frequency: float | list[float] = Field(
            default=True,
            name="Sampling frequency",
            description="Sampling frequency of probe.",
        )

        batch_size: int | list[int] = Field(
            default=60000,
            name="Batch size",
            description="Number of samples included in each batch of data.",
        )

        nblocks: int | list[int] = Field(
            default=1,
            name="Number of blocks",
            description="Number of non-overlapping blocks for drift correction \
                        (additional nblocks-1 blocks are created in the overlaps).",
        )

        Th_universal: float | list[float] = Field(
            default=10.0,
            name="Universal threshold",
            description="Spike detection threshold for universal templates.\
                            Th(1) in previous versions of Kilosort.",
        )

        Th_learned: float | list[float] = Field(
            default=8,
            name="Learned threshold",
            description="Spike detection threshold for learned templates.\
                            Th(2) in previous versions of Kilosort.",
        )

        tmin: float | list[float] = Field(
            default=-0.0015,
            name="tmin",
            description="Time in seconds when data used for sorting should begin.",
        )

        tmax: float | list[float] = Field(
            default=np.inf,
            name="tmax",
            description="Time in seconds when data used for sorting should end. By default,\
                            ends at the end of the recording.",
        )


    initialize: Initialize


class Kilosort4SingleConfig(Kilosort4ScanConfig, SingleCoordMixin):
    """Kilosort4SingleConfig."""

    parent_class: ClassVar = Kilosort4ScanConfig
    name: ClassVar[str] = "Kilosort4"
    description: ClassVar[str] = (
        "Kilosort4"
    )
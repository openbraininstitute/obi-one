"""Configuration for TRIBE v2 brain activity prediction task."""

import logging
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import Field, model_validator

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin

L = logging.getLogger(__name__)


class TribeBrainPredictionScanConfig(ScanConfig):
    """Predicts fMRI brain activity from video, audio, or text using TRIBE v2."""

    single_coord_class_name: ClassVar[str] = "TribeBrainPredictionSingleConfig"
    name: ClassVar[str] = "TRIBE v2 Brain Activity Prediction"
    description: ClassVar[str] = (
        "Predicts fMRI brain responses to naturalistic stimuli (video, audio, or text) "
        "using Meta's TRIBE v2 multimodal brain encoding model. Generates brain activity "
        "visualizations on the cortical surface."
    )

    class Stimulus(Block):
        """Input stimulus for brain activity prediction.

        Provide exactly one of video_path, audio_path, or text.
        When a video is provided, audio is automatically extracted and speech is
        transcribed to obtain word-level events. When text is provided, it is
        first converted to speech via text-to-speech.
        """

        video_path: Path | list[Path] | None = Field(
            default=None,
            description=(
                "Path to a video file (.mp4, .avi, .mkv, .mov, .webm). "
                "Audio and text are automatically extracted."
            ),
        )
        audio_path: Path | list[Path] | None = Field(
            default=None,
            description="Path to an audio file (.wav, .mp3, .flac, .ogg).",
        )
        text: str | list[str] | None = Field(
            default=None,
            description=(
                "Text content to predict brain responses for. "
                "Converted to speech internally before prediction."
            ),
        )
        start_time: float | None = Field(
            default=None,
            ge=0,
            description="Start time in seconds. Events before this are dropped.",
        )
        end_time: float | None = Field(
            default=None,
            ge=0,
            description="End time in seconds. Events after this are dropped.",
        )

    class Model(Block):
        """TRIBE v2 model configuration."""

        checkpoint: str = Field(
            default="facebook/tribev2",
            description=(
                "HuggingFace model ID or local path to a TRIBE v2 checkpoint directory "
                "containing config.yaml and best.ckpt."
            ),
        )
        device: str = Field(
            default="auto",
            description="Torch device for inference. 'auto' selects CUDA when available.",
        )
        cache_folder: str = Field(
            default="./tribe_cache",
            description="Directory for caching extracted features and downloaded models.",
        )
        config_update: dict | None = Field(
            default=None,
            description=(
                "Optional overrides for the TRIBE v2 config (dotted keys). "
                "E.g. {'data.text_feature.model_name': 'openai-community/gpt2'}."
            ),
        )

    class Visualization(Block):
        """Brain activity visualization settings."""

        output_video: bool = Field(
            default=True,
            description="Generate an MP4 video of brain activity over time.",
        )
        output_timesteps_image: bool = Field(
            default=True,
            description="Generate a static PNG image showing brain activity at each timestep.",
        )
        n_timesteps: int | None = Field(
            default=None,
            description=("Number of timesteps to visualize. None uses all available timesteps."),
        )
        cmap: str = Field(
            default="fire",
            description="Matplotlib colormap for brain surface rendering.",
        )
        norm_percentile: int = Field(
            default=99,
            ge=1,
            le=100,
            description="Percentile for robust normalization of brain activity values.",
        )
        views: Literal["left", "right", "dorsal", "ventral", "anterior", "posterior"] = Field(
            default="left",
            description="Brain viewing angle for visualization.",
        )
        show_stimuli: bool = Field(
            default=True,
            description="Show stimulus frames/text alongside brain activity in timesteps image.",
        )
        mesh: Literal["fsaverage3", "fsaverage4", "fsaverage5", "fsaverage6", "fsaverage7"] = Field(
            default="fsaverage5",
            description="Cortical surface mesh resolution for plotting.",
        )
        interpolated_fps: int | None = Field(
            default=10,
            ge=1,
            description="Interpolated FPS for output video. None disables interpolation.",
        )

    stimulus: Stimulus = Field(
        description="Input stimulus (video, audio, or text) for brain activity prediction.",
    )
    model: Model = Field(
        default_factory=Model,
        description="TRIBE v2 model settings.",
    )
    visualization: Visualization = Field(
        default_factory=Visualization,
        description="Brain activity visualization settings.",
    )

    @model_validator(mode="after")
    def validate_exactly_one_stimulus(self) -> "TribeBrainPredictionScanConfig":
        """Ensure exactly one stimulus input is provided."""
        provided = []
        if self.stimulus.video_path is not None:
            provided.append("video_path")
        if self.stimulus.audio_path is not None:
            provided.append("audio_path")
        if self.stimulus.text is not None:
            provided.append("text")
        if len(provided) != 1:
            msg = (
                f"Exactly one of video_path, audio_path, or text must be provided, "
                f"got: {provided or 'none'}"
            )
            raise ValueError(msg)
        return self


class TribeBrainPredictionSingleConfig(TribeBrainPredictionScanConfig, SingleConfigMixin):
    """Single (non-scan) configuration for TRIBE v2 brain activity prediction."""

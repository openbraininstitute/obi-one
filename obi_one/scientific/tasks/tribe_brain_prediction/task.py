"""TRIBE v2 brain activity prediction task."""

import json
import logging
from pathlib import Path

import entitysdk
import numpy as np
from fastapi import HTTPException
from pydantic import Field

from obi_one.core.task import Task
from obi_one.scientific.tasks.tribe_brain_prediction.config import (
    TribeBrainPredictionSingleConfig,
)

L = logging.getLogger(__name__)

_PREDICTIONS_FILENAME = "predictions.npy"
_EVENTS_FILENAME = "events.csv"
_METADATA_FILENAME = "prediction_metadata.json"
_TIMESTEPS_IMAGE_FILENAME = "brain_activity_timesteps.png"
_VIDEO_FILENAME = "brain_activity.mp4"


class TribeBrainPredictionTask(Task):
    """Predicts fMRI brain activity from stimuli using TRIBE v2.

    Loads the TRIBE v2 model, processes the input stimulus (video, audio, or text),
    runs brain activity prediction, and generates visualizations including a static
    timesteps image and/or an MP4 video of predicted cortical activity.
    """

    config: TribeBrainPredictionSingleConfig = Field(
        description="Configuration for TRIBE v2 brain activity prediction."
    )

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,  # noqa: ARG002
    ) -> dict:
        """Run TRIBE v2 brain activity prediction and generate outputs.

        Returns a dictionary with paths to generated output files and prediction metadata.
        """
        try:
            output_dir = Path(self.config.coordinate_output_root)
            output_dir.mkdir(parents=True, exist_ok=True)

            model, plotter = self._load_model_and_plotter()
            events = self._build_events(model, output_dir)
            preds, segments = self._run_prediction(model, events)
            return self._generate_outputs(preds, segments, events, plotter, output_dir)

        except Exception as e:
            L.exception("TRIBE v2 brain prediction failed")
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}") from e

    def _load_model_and_plotter(self) -> tuple:
        """Load the TRIBE v2 model and initialize the brain plotter."""
        from tribev2.demo_utils import TribeModel  # noqa: PLC0415
        from tribev2.plotting import PlotBrain  # noqa: PLC0415

        model_cfg = self.config.model
        vis_cfg = self.config.visualization

        L.info(
            "Loading TRIBE v2 model from '%s' on device '%s'",
            model_cfg.checkpoint,
            model_cfg.device,
        )

        model = TribeModel.from_pretrained(
            checkpoint_dir=model_cfg.checkpoint,
            cache_folder=model_cfg.cache_folder,
            device=model_cfg.device,
            config_update=model_cfg.config_update,
        )

        plotter = PlotBrain(mesh=vis_cfg.mesh)

        return model, plotter

    def _build_events(self, model: object, output_dir: Path) -> "pd.DataFrame":  # noqa: F821
        """Build an events DataFrame from the configured stimulus input."""
        stim = self.config.stimulus

        if stim.video_path is not None:
            L.info("Building events from video: %s", stim.video_path)
            events = model.get_events_dataframe(video_path=str(stim.video_path))

        elif stim.audio_path is not None:
            L.info("Building events from audio: %s", stim.audio_path)
            events = model.get_events_dataframe(audio_path=str(stim.audio_path))

        elif stim.text is not None:
            L.info("Building events from text input")
            text_path = output_dir / "_stimulus_text.txt"
            text_path.write_text(stim.text, encoding="utf-8")
            events = model.get_events_dataframe(text_path=str(text_path))

        else:
            msg = "No stimulus input provided."
            raise ValueError(msg)

        L.info("Built events DataFrame with %d rows", len(events))

        # Filter events to time bounds
        if stim.start_time is not None or stim.end_time is not None:
            events = self._filter_events_by_time(events, stim.start_time, stim.end_time)

        # Save events
        events_path = output_dir / _EVENTS_FILENAME
        events.to_csv(events_path, index=False)
        L.info("Saved events to %s", events_path)

        return events

    def _run_prediction(  # noqa: PLR6301
        self,
        model: object,
        events: "pd.DataFrame",  # noqa: F821
    ) -> tuple[np.ndarray, list]:
        """Run the TRIBE v2 model to predict brain activity."""
        L.info("Running TRIBE v2 brain activity prediction...")
        preds, segments = model.predict(events=events)
        L.info(
            "Prediction complete: %d timesteps x %d vertices",
            preds.shape[0],
            preds.shape[1],
        )
        return preds, segments

    def _generate_outputs(
        self,
        preds: np.ndarray,
        segments: list,
        events: "pd.DataFrame",  # noqa: ARG002, F821
        plotter: object,
        output_dir: Path,
    ) -> dict:
        """Save predictions and generate visualizations."""
        import matplotlib as mpl  # noqa: PLC0415

        mpl.use("Agg")
        import matplotlib.pyplot as plt  # noqa: PLC0415

        vis_cfg = self.config.visualization
        n_timesteps = vis_cfg.n_timesteps or preds.shape[0]
        n_timesteps = min(n_timesteps, preds.shape[0])

        preds_subset = preds[:n_timesteps]
        segments_subset = segments[:n_timesteps]

        # Save raw predictions
        preds_path = output_dir / _PREDICTIONS_FILENAME
        np.save(preds_path, preds)
        L.info("Saved predictions (%s) to %s", preds.shape, preds_path)

        # Save metadata
        metadata = {
            "n_timesteps_total": int(preds.shape[0]),
            "n_timesteps_visualized": n_timesteps,
            "n_vertices": int(preds.shape[1]),
            "checkpoint": self.config.model.checkpoint,
            "mesh": vis_cfg.mesh,
            "stimulus_type": self._get_stimulus_type(),
        }
        metadata_path = output_dir / _METADATA_FILENAME
        with metadata_path.open("w") as f:
            json.dump(metadata, f, indent=2)

        output_files = {
            "predictions": str(preds_path),
            "events": str(output_dir / _EVENTS_FILENAME),
            "metadata": str(metadata_path),
        }

        # Generate static timesteps image
        if vis_cfg.output_timesteps_image:
            timesteps_path = output_dir / _TIMESTEPS_IMAGE_FILENAME
            L.info("Generating timesteps image (%d timesteps)...", n_timesteps)
            fig = plotter.plot_timesteps(
                preds_subset,
                segments=segments_subset,
                cmap=vis_cfg.cmap,
                norm_percentile=vis_cfg.norm_percentile,
                vmin=0.6,
                alpha_cmap=(0, 0.2),
                show_stimuli=vis_cfg.show_stimuli,
                views=vis_cfg.views,
            )
            fig.savefig(timesteps_path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            L.info("Saved timesteps image to %s", timesteps_path)
            output_files["timesteps_image"] = str(timesteps_path)

        # Generate MP4 video
        if vis_cfg.output_video:
            video_path = output_dir / _VIDEO_FILENAME
            L.info("Generating brain activity video (%d frames)...", n_timesteps)
            plotter.plot_timesteps_mp4(
                preds_subset,
                filepath=str(video_path),
                segments=segments_subset,
                cmap=vis_cfg.cmap,
                norm_percentile=vis_cfg.norm_percentile,
                interpolated_fps=vis_cfg.interpolated_fps,
                views=vis_cfg.views,
            )
            L.info("Saved brain activity video to %s", video_path)
            output_files["video"] = str(video_path)

        L.info("TRIBE v2 brain prediction task completed successfully")
        return output_files

    @staticmethod
    def _filter_events_by_time(
        events: "pd.DataFrame",  # noqa: F821
        start_time: float | None,
        end_time: float | None,
    ) -> "pd.DataFrame":  # noqa: F821
        """Keep only events overlapping [start_time, end_time] and clip them to fit."""
        if "duration" in events.columns:
            event_end = events["start"] + events["duration"]
        else:
            event_end = events["start"]

        mask = True  # noqa: NPY003
        if start_time is not None:
            mask = mask & (event_end > start_time)
        if end_time is not None:
            mask = mask & (events["start"] < end_time)

        filtered = events.loc[mask].copy()

        # Clip start/duration to the requested window
        if start_time is not None and "duration" in filtered.columns:
            overshoot = start_time - filtered["start"]
            clip = overshoot.clip(lower=0)
            filtered["start"] = filtered["start"] + clip
            filtered["duration"] = filtered["duration"] - clip
        if end_time is not None and "duration" in filtered.columns:
            excess = (filtered["start"] + filtered["duration"]) - end_time
            filtered["duration"] = filtered["duration"] - excess.clip(lower=0)

        if "stop" in filtered.columns:
            filtered["stop"] = filtered["start"] + filtered["duration"]

        n_dropped = len(events) - len(filtered)
        L.info(
            "Time filter [%s, %s]: kept %d events, dropped %d",
            start_time,
            end_time,
            len(filtered),
            n_dropped,
        )
        return filtered.reset_index(drop=True)

    def _get_stimulus_type(self) -> str:
        """Return the type of stimulus used."""
        stim = self.config.stimulus
        if stim.video_path is not None:
            return "video"
        if stim.audio_path is not None:
            return "audio"
        return "text"

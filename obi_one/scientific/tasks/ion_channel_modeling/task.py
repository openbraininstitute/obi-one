"""Ion channel modeling task."""

import json
import pickle  # ruff: ignore[suspicious-pickle-import]
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import uuid
from pathlib import Path
from typing import Any

from entitysdk.client import Client
from entitysdk.models import IonChannelModel, NeuronBlock
from entitysdk.types import AssetLabel, ContentType

from obi_one.core.task import Task
from obi_one.scientific.from_id.ion_channel_recording_from_id import IonChannelRecordingFromID
from obi_one.scientific.tasks.ion_channel_modeling.config import (
    IonChannelFittingSingleConfig,
    ResolvedModelProperties,
    generic_subject,
)
from obi_one.utils.process import run_and_log

try:
    from ion_channel_builder.create_model.main import (  # ty:ignore[unresolved-import]
        extract_all_equations,
    )
    from ion_channel_builder.io.write_output import (  # ty:ignore[unresolved-import]
        get_range_params_with_units,
        write_vgate_output,
    )
    from ion_channel_builder.run_model.run_model import (  # ty:ignore[unresolved-import]
        run_ion_channel_model,
    )
except ImportError:

    def extract_all_equations(
        data_paths: list[Path],
        ljps: list,
        eq_names: list[str],
        voltage_exclusion: dict,
        stim_timings: dict,
        stim_timings_corrections: dict,
        output_folder: Path,
        **kwargs: Any,
    ) -> None:
        pass

    def get_range_params_with_units(eq_names: dict[str, str]) -> list[dict[str, str | None]]:
        msg = "ion_channel_builder is required"
        raise NotImplementedError(msg)

    def write_vgate_output(
        eq_names: dict[str, str],
        eq_popt: dict[str, list[float]],
        suffix: str,
        ion: str,
        m_power: int,
        h_power: int,
        output_name: str,
        channel_type: str = "kv",
        erev: float | None = None,
    ) -> None:
        pass

    def run_ion_channel_model(
        mech_suffix: str,
        # current is defined like this in mod file, see ion_channel_builder.io.write_output
        mech_current: float,
        # no need to actually give temperature because model is not temperature-dependent
        temperature: float,
        mech_conductance_name: str,
        output_folder: Path,
        savefig: bool,  # ruff: ignore[boolean-type-hint-positional-argument]
        show: bool,  # ruff: ignore[boolean-type-hint-positional-argument]
        **kwargs: Any,
    ) -> None:
        pass


VOLTAGE_EXCLUSION = {
    "activation": {"above": None, "below": None},
    "inactivation": {"above": None, "below": None},
}

# None means "read the timing from the trace"; the corrections shift those read timings, in ms.
STIM_TIMINGS = {
    "activation": {"start": None, "end": None},
    "inactivation_iv": {"start": None, "end": None},
    "inactivation_tc": {"start": None, "end": None},
}

STIM_TIMINGS_CORRECTIONS = {
    "activation": {"start": 0.0, "end": -1.0},
    "inactivation_iv": {"start": 5.0, "end": -1.0},
    "inactivation_tc": {"start": 0.0, "end": -1.0},
}


PLOT_FITTED_MODEL_COMMAND = (
    "import sys\n"
    "from obi_one.scientific.tasks.ion_channel_modeling.task import plot_fitted_model\n"
    "plot_fitted_model(sys.argv[1])"
)


def plot_fitted_model(io_path: str) -> None:
    """Child side of plot_in_fresh_process: reads its arguments from io_path, writes the result."""
    import neuron  # ruff: ignore[import-outside-top-level]

    mechanisms_root, kwargs = pickle.loads(Path(io_path).read_bytes())  # ruff: ignore[suspicious-pickle-usage]
    if not neuron.load_mechanisms(str(mechanisms_root)):
        msg = f"No compiled mechanisms found in {mechanisms_root}"
        raise RuntimeError(msg)
    Path(io_path).write_bytes(pickle.dumps(run_ion_channel_model(**kwargs)))


def plot_in_fresh_process(mechanisms_root: Path, **kwargs: Any) -> Any:
    """NEURON loads a mechanism name only once per process, and every fit of a sweep compiles its
    own mechanism under the same name.

    A new interpreter rather than multiprocessing's spawn, which re-runs the caller's script.
    """
    io_path = mechanisms_root / "plot_fitted_model.pkl"
    io_path.write_bytes(pickle.dumps((mechanisms_root, kwargs)))
    try:
        run_and_log([sys.executable, "-c", PLOT_FITTED_MODEL_COMMAND, str(io_path)])
    except subprocess.CalledProcessError as e:
        # The child's exception, rather than its exit status.
        raise RuntimeError(e.stderr.strip().rpartition("\n")[2] or str(e)) from e
    return pickle.loads(io_path.read_bytes())  # ruff: ignore[suspicious-pickle-usage]


class IonChannelFittingTask(Task):
    config: IonChannelFittingSingleConfig

    @property
    def recordings(self) -> tuple[IonChannelRecordingFromID, ...]:
        return self.config.initialize.recordings

    @staticmethod
    def conductance_name(ion_channel_name: str) -> str:
        return f"g{ion_channel_name}bar"

    def download_input(
        self,
        db_client: Client,
    ) -> tuple[list[Path], list[float]]:
        """Download every recording, and return their traces and ljp values."""
        trace_paths = []
        trace_ljps = []
        for recording in self.recordings:
            trace_paths.append(
                # One folder per recording: NWB files of different recordings can share a name.
                recording.download_asset(
                    dest_dir=self.config.coordinate_output_root / "recordings" / recording.id_str,
                    db_client=db_client,
                )
            )
            trace_ljps.append(recording.entity(db_client=db_client).ljp)
        return trace_paths, trace_ljps

    @staticmethod
    def register_json(client: Client, id_: str | uuid.UUID, json_path: str | Path) -> None:
        client.upload_file(
            entity_id=uuid.UUID(str(id_)),
            entity_type=IonChannelModel,
            file_path=Path(json_path),
            file_content_type=ContentType.application_json,
            asset_label=AssetLabel.ion_channel_model_figure_summary_json,
        )

    @staticmethod
    def register_thumbnail(
        client: Client, id_: str | uuid.UUID, path_to_register: str | Path
    ) -> None:
        client.upload_file(
            entity_id=uuid.UUID(str(id_)),
            entity_type=IonChannelModel,
            file_path=Path(path_to_register),
            file_content_type=ContentType.image_png,
            asset_label=AssetLabel.ion_channel_model_thumbnail,
        )

    def cleanup_dict(self, d: Any) -> Any:
        if isinstance(d, Path):
            return str(d.name)
        if isinstance(d, dict):
            return {key: self.cleanup_dict(value) for key, value in d.items() if key != "thumbnail"}
        return d

    @staticmethod
    def register_plots(
        client: Client, id_: str | uuid.UUID, paths_to_register: list[str | Path]
    ) -> None:
        for path in paths_to_register:
            client.upload_file(
                entity_id=uuid.UUID(str(id_)),
                entity_type=IonChannelModel,
                file_path=Path(path),
                file_content_type=ContentType.application_pdf,
                asset_label=AssetLabel.ion_channel_model_figure,
            )

    def register_plots_and_json(
        self, db_client: Client, figure_filepaths: dict, model_id: str | uuid.UUID
    ) -> None:
        # get the paths of the pdf figures
        figure_types = ["traces", "stimuli", "steady state", "time constant"]
        paths_to_register = [
            value
            for key1, d in figure_filepaths.items()
            if key1 != "thumbnail"
            for key, value in d.items()
            if key in figure_types
        ]
        figure_summary_dict = self.cleanup_dict(figure_filepaths)
        json_path = self.config.coordinate_output_root / "figure_summary.json"
        with json_path.open("w") as f:
            json.dump(figure_summary_dict, f, indent=4)

        self.register_plots(db_client, model_id, paths_to_register)
        if "thumbnail" in figure_filepaths:
            self.register_thumbnail(db_client, model_id, figure_filepaths["thumbnail"])

        if figure_summary_dict != {}:
            self.register_json(db_client, model_id, json_path)

    def save(
        self,
        mod_filepath: Path,
        figure_filepaths: dict[Path],  # ty:ignore[invalid-type-arguments]
        db_client: Client,
        range_vars: list[dict[str, str | None]],
        properties: ResolvedModelProperties,
    ) -> uuid.UUID:
        # reproduce here what is being done in ion_channel_builder.io.write_output
        neuron_block = NeuronBlock(
            **{"global": [{"celsius": "degree C"}]},
            range=range_vars,
            **self.config.model_type.neuron_block_currents(),
        )

        recording_names = ", ".join(
            str(recording.entity(db_client=db_client).name) for recording in self.recordings
        )

        subject = properties.subject or generic_subject(
            properties.species, properties.strain, db_client=db_client
        )

        model = db_client.register_entity(
            IonChannelModel(
                name=self.config.info.campaign_name,
                nmodl_suffix=properties.ion_channel_name,
                description=(
                    f"Ion channel model: {properties.ion_channel_name}.mod "
                    f"made using recordings: {recording_names} "
                    f"for (temperature: {properties.temperature}), "
                    f"brain region: {properties.brain_region.name}, "
                    f"and subject: {subject.name}."
                ),
                contributions=None,  # TODO: fix this
                is_ljp_corrected=True,
                is_temperature_dependent=False,
                temperature_celsius=properties.temperature,
                is_stochastic=False,
                neuron_block=neuron_block,
                brain_region=properties.brain_region,
                subject=subject,
                conductance_name=self.conductance_name(properties.ion_channel_name),
                max_permeability_name=None,
            )
        )

        _ = db_client.upload_file(
            entity_id=model.id,
            entity_type=IonChannelModel,
            file_path=mod_filepath,
            file_content_type=ContentType.application_mod,
            asset_label=AssetLabel.neuron_mechanisms,
        )

        self.register_plots_and_json(db_client, figure_filepaths, model.id)

        return model.id

    def execute(
        self,
        *,
        db_client: Client,
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
        execution_activity_id: str | None = None,
    ) -> str:  # returns the id of the generated ion channel model
        """Download traces from entitycore, use them to build an ion channel, then register it."""
        execution_activity = self._get_execution_activity(
            db_client=db_client, execution_activity_id=execution_activity_id
        )

        try:  # ruff: ignore[too-many-statements-in-try-clause]
            properties = self.config.resolve_model_properties(
                [recording.entity(db_client=db_client) for recording in self.recordings],
                db_client=db_client,
            )

            # download traces asset and metadata given id.
            # Get ljp (liquid junction potential) voltage corection from metadata
            trace_paths, trace_ljps = self.download_input(db_client=db_client)

            model = self.config.model_type
            eq_names = model.eq_names()
            # run ion_channel_builder main function to get optimised parameters
            eq_popt = extract_all_equations(
                data_paths=trace_paths,
                ljps=trace_ljps,
                eq_names=eq_names,  # ty:ignore[invalid-argument-type]
                voltage_exclusion=VOLTAGE_EXCLUSION,
                stim_timings=STIM_TIMINGS,
                stim_timings_corrections=STIM_TIMINGS_CORRECTIONS,
                output_folder=self.config.coordinate_output_root,
                **model.fitting_options(),
            )

            # create new mod file
            coordinate_root = Path(self.config.coordinate_output_root).resolve()
            mechanisms_dir = coordinate_root / "mechanisms"
            mechanisms_dir.mkdir(parents=True, exist_ok=True)
            output_name = mechanisms_dir / f"{properties.ion_channel_name}.mod"

            write_vgate_output(
                eq_names=eq_names,
                eq_popt=eq_popt,  # ty:ignore[invalid-argument-type]
                suffix=properties.ion_channel_name,
                output_name=output_name,  # ty:ignore[invalid-argument-type]
                **model.mod_file_options(),
            )

            # Compile into the coordinate folder rather than the process cwd, which concurrent
            # fits in one worker share. The path is relative because make stops on the "=" of
            # NAME_EQUALS_VALUE coordinate folders.
            run_and_log(
                ["nrnivmodl", "-incflags", "-DDISABLE_REPORTINGLIB", mechanisms_dir.name],
                cwd=coordinate_root,
            )

            mech_suffix = properties.ion_channel_name
            figure_paths_dict = plot_in_fresh_process(
                coordinate_root,
                mech_suffix=mech_suffix,
                # current is defined like this in mod file, see
                # ion_channel_builder.io.write_output
                mech_current=model.current,
                temperature=properties.temperature,
                mech_conductance_name=self.conductance_name(mech_suffix),
                output_folder=self.config.coordinate_output_root,
                savefig=True,
                show=False,
                **model.plot_options,
            )

            # those are hardcoded in ion-channel-builder.io.templates.mod_template.jinja2
            range_vars = [
                {f"g{mech_suffix}bar": "S/cm2"},
                {f"g{mech_suffix}": "S/cm2"},
                {model.current: "mA/cm2"},
                *model.gating_range_vars,
            ]
            range_vars += get_range_params_with_units(eq_names)

            # register the mod file and figures to the platform
            model_id = self.save(
                mod_filepath=output_name,
                figure_filepaths=figure_paths_dict,
                db_client=db_client,
                range_vars=range_vars,  # ty:ignore[invalid-argument-type]
                properties=properties,
            )

            self._update_execution_activity(
                db_client=db_client,
                execution_activity=execution_activity,
                generated=[str(model_id)],
            )

        except Exception as e:
            error_message = f"Ion channel modeling failed: {e}"
            raise Exception(error_message) from e  # ruff: ignore[raise-vanilla-class]
        else:
            return model_id  # ty:ignore[invalid-return-type]

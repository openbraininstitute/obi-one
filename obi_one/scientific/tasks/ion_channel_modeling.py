"""Ion channel modeling scan config.

Fits a Hodgkin-Huxley channel model to a set of ion channel recordings: one equation per
gating variable, fitted by `ion_channel_builder`, written out as a mod file and registered
as an IonChannelModel.

Several recordings are fitted *together* into one model, not one model each — which is what
`extract_all_equations` takes lists of traces and ljps for. The four equations are keys on
one model block rather than separately referenced blocks, so the editor draws the whole model
as a single element.
"""

import json
import logging
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal

import entitysdk
from entitysdk import models
from entitysdk.types import AssetLabel, ContentType
from pydantic import Discriminator, Field, StringConstraints

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.serialization_constants import COORDINATE_CONFIG_FILENAME, SCAN_CONFIG_FILENAME
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.blocks.ion_channel_equations.ion_channel_equations import (
    EquationKey,
    equation_schema_extra,
)
from obi_one.scientific.from_id.ion_channel_recording_from_id import IonChannelRecordingFromID

L = logging.getLogger(__name__)

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
    ) -> None:
        pass

    def get_range_params_with_units(eq_names: dict[str, str]) -> list[dict[str, str | None]]:  # ty:ignore[empty-body]
        pass

    def write_vgate_output(
        eq_names: dict[str, str],
        eq_popt: dict[str, list[float]],
        suffix: str,
        ion: str,
        m_power: int,
        h_power: int,
        output_name: str,
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
    ) -> None:
        pass


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    MODEL = "Model"


class HodgkinHuxleyIonChannelModel(Block):
    """The channel model to fit: one equation per gating variable, plus their exponents."""

    title: ClassVar[str] = "Hodgkin-Huxley ion channel model"

    m_power: int | list[int] = Field(
        title="m exponent in channel equation",
        default=1,
        ge=1,
        le=4,
        description=(
            r"Exponent \(p\) of \(m\) in the channel equation: "
            r"\(g = \bar{g} \cdot m^p \cdot h^q\)"
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    h_power: int | list[int] = Field(
        title="h exponent in channel equation",
        default=1,
        ge=0,
        le=4,
        description=(
            r"Exponent \(q\) of \(h\) in the channel equation: "
            r"\(g = \bar{g} \cdot m^p \cdot h^q\)"
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )

    minf_eq: Literal[EquationKey.SIG_FIT_MINF] = Field(
        title="m∞ equation",
        description=(
            r"Steady state activation parameter \( m_{\infty} \) equation. "
            r"This equation will be used for solving the differential equation: "
            r"\( \frac{dm}{dt} = \frac{m_{\infty} - m}{\tau_{m}} \)"
        ),
        default=EquationKey.SIG_FIT_MINF,
        json_schema_extra=equation_schema_extra(EquationKey.SIG_FIT_MINF),
    )

    mtau_eq: Literal[
        EquationKey.SIG_FIT_MTAU,
        EquationKey.THERMO_FIT_MTAU,
        EquationKey.THERMO_FIT_MTAU_V2,
        EquationKey.BELL_FIT_MTAU,
    ] = Field(
        title="m time constant equation",
        description=(
            r"Activation time constant \(\tau_m\) equation. "
            r"This equation will be used for solving the differential equation: "
            r"\( \frac{dm}{dt} = \frac{m_{\infty} - m}{\tau_{m}} \)"
        ),
        default=EquationKey.SIG_FIT_MTAU,
        json_schema_extra=equation_schema_extra(
            EquationKey.SIG_FIT_MTAU,
            EquationKey.THERMO_FIT_MTAU,
            EquationKey.THERMO_FIT_MTAU_V2,
            EquationKey.BELL_FIT_MTAU,
        ),
    )

    hinf_eq: Literal[EquationKey.SIG_FIT_HINF] = Field(
        title="h∞ equation",
        description=(
            r"Steady state inactivation parameter \(h_{\infty}\) equation. "
            r"This equation will be used for solving the differential equation: "
            r"\( \frac{dh}{dt} = \frac{h_{\infty} - h}{\tau_{h}} \)"
        ),
        default=EquationKey.SIG_FIT_HINF,
        json_schema_extra=equation_schema_extra(EquationKey.SIG_FIT_HINF),
    )

    htau_eq: Literal[EquationKey.SIG_FIT_HTAU] = Field(
        title="h time constant equation",
        description=(
            r"Inactivation time constant \(\tau_h\) equation. "
            r"This equation will be used for solving the differential equation: "
            r"\( \frac{dh}{dt} = \frac{h_{\infty} - h}{\tau_{h}} \)"
        ),
        default=EquationKey.SIG_FIT_HTAU,
        json_schema_extra=equation_schema_extra(EquationKey.SIG_FIT_HTAU),
    )


# One member, but a discriminated union rather than a bare block: the editor draws it as a
# block_union, so a second channel formalism becomes another member and nothing else changes.
IonChannelModelUnion = Annotated[HodgkinHuxleyIonChannelModel, Discriminator("type")]


class IonChannelFittingScanConfig(ScanConfig):
    """Form for modeling an ion channel model from a set of ion channel traces."""

    name: ClassVar[str] = "Ion channel"
    description: ClassVar[str] = "Models ion channel model from a set of ion channel traces."

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP,
            BlockGroup.MODEL,
        ],
    }

    class Initialize(Block):
        recordings: tuple[IonChannelRecordingFromID, ...] = Field(
            title="Ion channel recordings",
            description=(
                "The recordings to fit the channel model to. Several are fitted jointly into "
                "one model, not one model each."
            ),
            min_length=1,
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER_MULTIPLE},
        )

        ion_channel_name: Annotated[str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")] = (
            Field(
                title="Ion channel name",
                description=(
                    "The name you want to give to the generated ion channel model "
                    "(used as SUFFIX in the mod file). "
                    "Name must start with a letter or underscore, and can only contain "
                    "letters, numbers, and underscores."
                ),
                min_length=1,
                default="DefaultIonChannelName",
                json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
            )
        )

    info: Info = Field(
        title="Info",
        description="Information about the ion channel modeling campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the fitting.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    model_type: IonChannelModelUnion = Field(
        title="Ion Channel Model",
        description=(
            "The Hodgkin-Huxley channel model to fit: an equation per gating variable, and "
            "the exponents p and q of m and h in the channel equation g = gbar * m^p * h^q."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_UNION,
            SchemaKey.GROUP: BlockGroup.MODEL,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    def input_recordings(self, db_client: entitysdk.client.Client) -> list:
        """The recording entities this config fits."""
        return [recording.entity(db_client=db_client) for recording in self.initialize.recordings]

    def create_campaign_entity_with_config(
        self,
        output_root: Path,
        multiple_value_parameters_dictionary: dict | None = None,
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
    ) -> entitysdk.models.IonChannelModelingCampaign:  # ty:ignore[possibly-missing-submodule]
        """Initializes the ion channel modeling campaign in the database."""
        L.info("1. Initializing ion channel modeling campaign in the database...")
        if multiple_value_parameters_dictionary is None:
            multiple_value_parameters_dictionary = {}

        L.info("-- Register IonChannelModelingCampaign Entity")
        self._campaign = db_client.register_entity(
            entitysdk.models.IonChannelModelingCampaign(  # ty:ignore[possibly-missing-submodule]
                name=self.info.campaign_name,
                description=self.info.campaign_description,
                input_recordings=self.input_recordings(db_client),
                scan_parameters=multiple_value_parameters_dictionary,
            )
        )

        L.info("-- Upload campaign_generation_config")
        _ = db_client.upload_file(
            entity_id=self._campaign.id,
            entity_type=entitysdk.models.IonChannelModelingCampaign,  # ty:ignore[possibly-missing-submodule]
            file_path=output_root / SCAN_CONFIG_FILENAME,
            file_content_type="application/json",  # ty:ignore[invalid-argument-type]
            asset_label="campaign_generation_config",  # ty:ignore[invalid-argument-type]
        )

        return self._campaign

    def create_campaign_generation_entity(
        self,
        ion_channel_modelings: list[entitysdk.models.IonChannelModelingConfig],  # ty:ignore[possibly-missing-submodule]
        db_client: entitysdk.client.Client,
    ) -> None:  # ty:ignore[invalid-method-override]
        """Register the activity generating the ion channel modeling tasks in the database."""
        L.info("3. Saving completed ion channel modeling campaign generation")

        L.info("-- Register IonChannelModelingGeneration Entity")
        db_client.register_entity(
            entitysdk.models.IonChannelModelingConfigGeneration(  # ty:ignore[possibly-missing-submodule]
                start_time=datetime.now(UTC),
                used=[self._campaign],
                generated=ion_channel_modelings,
            )
        )


class IonChannelFittingSingleConfig(IonChannelFittingScanConfig, SingleConfigMixin):
    """Only allows single values and ensures nested attributes follow the same rule."""

    def create_single_entity_with_config(
        self,
        campaign: entitysdk.models.IonChannelModelingCampaign,  # ty:ignore[possibly-missing-submodule]
        db_client: entitysdk.client.Client,
    ) -> entitysdk.models.IonChannelModelingConfig:  # ty:ignore[possibly-missing-submodule]
        """Saves the simulation to the database."""
        L.info(f"2.{self.idx} Saving ion channel modeling config {self.idx} to database...")

        # For now, we only support a single recording
        recordings = self.initialize.recordings
        if not isinstance(recordings, IonChannelRecordingFromID):
            msg = (
                "IonChannelModeling currently only supports a single IonChannelRecordingFromID. "
                f"Got {type(recordings).__name__}"
            )
            raise OBIONEError(msg)

        L.info("-- Register IonChannelModeling Entity")
        self._single_entity = db_client.register_entity(
            entitysdk.models.IonChannelModelingConfig(  # ty:ignore[possibly-missing-submodule]
                name=f"IonChannelModelingConfig {self.idx}",
                description=f"IonChannelModelingConfig {self.idx}",
                scan_parameters=self.single_coordinate_scan_params.dictionary_representation(),
                ion_channel_modeling_campaign_id=campaign.id,
            )
        )

        L.info("-- Upload ion_channel_modeling_generation_config")
        _ = db_client.upload_file(
            entity_id=self.single_entity.id,
            entity_type=entitysdk.models.IonChannelModelingConfig,  # ty:ignore[possibly-missing-submodule]
            file_path=Path(self.coordinate_output_root, COORDINATE_CONFIG_FILENAME),
            file_content_type="application/json",  # ty:ignore[invalid-argument-type]
            asset_label="ion_channel_modeling_generation_config",  # ty:ignore[invalid-argument-type]
        )


class IonChannelFittingTask(Task):
    config: IonChannelFittingSingleConfig

    @property
    def recordings(self) -> tuple[IonChannelRecordingFromID, ...]:
        """The recordings this task fits, jointly, into one model."""
        return self.config.initialize.recordings

    def describing_recording(self, db_client: entitysdk.client.Client) -> Any:
        """The recording whose metadata describes the fitted model.

        A model carries one temperature, one subject and one brain region, and declares itself
        temperature-independent — so fitting across recordings that disagree on temperature
        would label the result with a number that is not true of it. The rest of the metadata
        comes from the first recording, which that check makes representative of the set.
        """
        entities = [recording.entity(db_client=db_client) for recording in self.recordings]
        temperatures = {entity.temperature for entity in entities}  # ty:ignore[unresolved-attribute]
        if len(temperatures) > 1:
            msg = (
                "Ion channel recordings fitted together must share a temperature, because the "
                f"fitted model records a single one. Got {sorted(temperatures)}."
            )
            raise OBIONEError(msg)
        return entities[0]

    @property
    def conductance_name(self) -> str:
        """The conductance name for the generated ion channel model."""
        return f"g{self.config.initialize.ion_channel_name}bar"

    @property
    def equation_keys(self) -> dict[str, str]:
        """The `ion_channel_builder` equation key chosen for each gating variable."""
        model = self.config.model_type
        return {
            "minf": model.minf_eq,
            "mtau": model.mtau_eq,
            "hinf": model.hinf_eq,
            "htau": model.htau_eq,
        }

    @property
    def m_power(self) -> int:
        """The exponent of m in the Hodgkin-Huxley channel equation."""
        return self.config.model_type.m_power  # ty:ignore[invalid-return-type]

    @property
    def h_power(self) -> int:
        """The exponent of h in the Hodgkin-Huxley channel equation."""
        return self.config.model_type.h_power  # ty:ignore[invalid-return-type]

    def download_input(
        self,
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
    ) -> tuple[list[Path], list[float]]:
        """Download every recording, and return their traces and ljp values.

        `extract_all_equations` fits one model from all of them together, which is why these
        are lists rather than a single trace.
        """
        trace_paths = []
        trace_ljps = []
        for recording in self.recordings:
            trace_paths.append(
                recording.download_asset(
                    dest_dir=self.config.coordinate_output_root, db_client=db_client
                )
            )
            trace_ljps.append(recording.entity(db_client=db_client).ljp)  # ty:ignore[unresolved-attribute]
        return trace_paths, trace_ljps

    @staticmethod
    def register_json(
        client: entitysdk.client.Client, id_: str | uuid.UUID, json_path: str | Path
    ) -> None:
        client.upload_file(
            entity_id=id_,  # ty:ignore[invalid-argument-type]
            entity_type=models.IonChannelModel,
            file_path=json_path,  # ty:ignore[invalid-argument-type]
            file_content_type=ContentType.application_json,
            asset_label=AssetLabel.ion_channel_model_figure_summary_json,
        )

    @staticmethod
    def register_thumbnail(
        client: entitysdk.client.Client, id_: str | uuid.UUID, path_to_register: str | Path
    ) -> None:
        client.upload_file(
            entity_id=id_,  # ty:ignore[invalid-argument-type]
            entity_type=models.IonChannelModel,
            file_path=path_to_register,  # ty:ignore[invalid-argument-type]
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
        client: entitysdk.client.Client, id_: str | uuid.UUID, paths_to_register: list[str | Path]
    ) -> None:
        for path in paths_to_register:
            client.upload_file(
                entity_id=id_,  # ty:ignore[invalid-argument-type]
                entity_type=models.IonChannelModel,
                file_path=path,  # ty:ignore[invalid-argument-type]
                file_content_type=ContentType.application_pdf,
                asset_label=AssetLabel.ion_channel_model_figure,
            )

    def register_plots_and_json(
        self, db_client: entitysdk.client.Client, figure_filepaths: dict, model_id: str | uuid.UUID
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
        db_client: entitysdk.client.Client,
        range_vars: list[dict[str, str | None]],
    ) -> None:
        # reproduce here what is being done in ion_channel_builder.io.write_output
        useion = entitysdk.models.UseIon(  # ty:ignore[possibly-missing-submodule]
            ion_name="k",  # TODO: fix this
            read=["ek"],
            write=["ik"],
            valence=1,  # putting 1 for K for now. TODO: fix this
            main_ion=True,
        )
        neuron_block = entitysdk.models.NeuronBlock(  # ty:ignore[possibly-missing-submodule]
            **{"global": [{"celsius": "degree C"}]},
            range=range_vars,
            useion=[useion],
            nonspecific=[],
        )

        # Get recording entity to access metadata
        recording_entity = self.describing_recording(db_client)

        # Extract subject and brain_region from recording metadata
        subject = recording_entity.subject
        brain_region = recording_entity.brain_region

        model = db_client.register_entity(
            entitysdk.models.IonChannelModel(  # ty:ignore[possibly-missing-submodule]
                name=self.config.info.campaign_name,
                nmodl_suffix=self.config.initialize.ion_channel_name,
                description=(
                    f"Ion channel model: {self.config.initialize.ion_channel_name}.mod "
                    f"made using recording: {recording_entity.name} "
                    f"for (temperature: {recording_entity.temperature}), "
                    f"brain region: {brain_region.name}, "
                    f"and subject: {subject.name}."
                ),
                contributions=None,  # TODO: fix this
                is_ljp_corrected=True,
                is_temperature_dependent=False,
                temperature_celsius=recording_entity.temperature,
                is_stochastic=False,
                neuron_block=neuron_block,
                brain_region=brain_region,
                subject=subject,
                conductance_name=self.conductance_name,
                max_permeability_name=None,
            )
        )

        _ = db_client.upload_file(
            entity_id=model.id,
            entity_type=entitysdk.models.IonChannelModel,  # ty:ignore[possibly-missing-submodule]
            file_path=mod_filepath,
            file_content_type=ContentType.application_mod,
            asset_label="neuron_mechanisms",  # ty:ignore[invalid-argument-type]
        )

        self.register_plots_and_json(db_client, figure_filepaths, model.id)

        return model.id

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
        execution_activity_id: str | None = None,  # ruff: ignore[unused-method-argument]
    ) -> str:  # returns the id of the generated ion channel model
        """Download traces from entitycore, use them to build an ion channel, then register it."""
        try:  # ruff: ignore[too-many-statements-in-try-clause]
            # download traces asset and metadata given id.
            # Get ljp (liquid junction potential) voltage corection from metadata
            trace_paths, trace_ljps = self.download_input(db_client=db_client)

            # prepare data to feed
            eq_names = self.equation_keys
            voltage_exclusion = {
                "activation": {
                    "above": None,
                    "below": None,
                },
                "inactivation": {
                    "above": None,
                    "below": None,
                },
            }
            stim_timings = {
                "activation": {
                    "start": None,
                    "end": None,
                },
                "inactivation_iv": {
                    "start": None,
                    "end": None,
                },
                "inactivation_tc": {
                    "start": None,
                    "end": None,
                },
            }
            stim_timings_corrections = {
                "activation": {
                    "start": 0.0,
                    "end": -1.0,
                },
                "inactivation_iv": {
                    "start": 5.0,
                    "end": -1.0,
                },
                "inactivation_tc": {
                    "start": 0.0,
                    "end": -1.0,
                },
            }
            # run ion_channel_builder main function to get optimised parameters
            eq_popt = extract_all_equations(
                data_paths=trace_paths,
                ljps=trace_ljps,
                eq_names=eq_names,  # ty:ignore[invalid-argument-type]
                voltage_exclusion=voltage_exclusion,
                stim_timings=stim_timings,
                stim_timings_corrections=stim_timings_corrections,
                output_folder=self.config.coordinate_output_root,
            )

            # create new mod file
            mechanisms_dir = self.config.coordinate_output_root / "mechanisms"
            mechanisms_dir.mkdir(parents=True, exist_ok=True)
            output_name = mechanisms_dir / f"{self.config.initialize.ion_channel_name}.mod"

            write_vgate_output(
                eq_names=eq_names,
                eq_popt=eq_popt,  # ty:ignore[invalid-argument-type]
                suffix=self.config.initialize.ion_channel_name,
                ion="k",
                m_power=self.m_power,
                h_power=self.h_power,
                output_name=output_name,  # ty:ignore[invalid-argument-type]
            )

            # compile output mod file
            subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
                [  # ruff: ignore[start-process-with-partial-path]
                    "nrnivmodl",
                    "-incflags",
                    "-DDISABLE_REPORTINGLIB",
                    str(mechanisms_dir),
                ],
                check=True,
            )

            # Get recording entity to access temperature
            recording_entity = self.describing_recording(db_client)

            mech_suffix = self.config.initialize.ion_channel_name
            # run ion_channel_builder mod file runner to produce plots
            figure_paths_dict = run_ion_channel_model(
                mech_suffix=mech_suffix,
                # current is defined like this in mod file, see ion_channel_builder.io.write_output
                mech_current="ik",  # ty:ignore[invalid-argument-type]
                temperature=recording_entity.temperature,
                mech_conductance_name=self.conductance_name,
                output_folder=self.config.coordinate_output_root,
                savefig=True,
                show=False,
            )

            # those are hardcoded in ion-channel-builder.io.templates.mod_template.jinja2
            range_vars = [
                {f"g{mech_suffix}bar": "S/cm2"},
                {f"g{mech_suffix}": "S/cm2"},
                {"ik": "mA/cm2"},
                {"mInf": None},
                {"mTau": "ms"},
                {"hInf": None},
                {"hTau": "ms"},
            ]
            range_vars += get_range_params_with_units(eq_names)

            # register the mod file and figures to the platform
            model_id = self.save(
                mod_filepath=output_name,
                figure_filepaths=figure_paths_dict,  # ty:ignore[invalid-argument-type]
                db_client=db_client,
                range_vars=range_vars,  # ty:ignore[invalid-argument-type]
            )

        except Exception as e:
            error_message = f"Ion channel modeling failed: {e}"
            raise Exception(error_message) from e  # ruff: ignore[raise-vanilla-class]
        else:
            return model_id  # ty:ignore[invalid-return-type]

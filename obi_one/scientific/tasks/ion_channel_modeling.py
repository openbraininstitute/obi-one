"""Ion channel modeling scan config."""

import json
import logging
import pickle  # ruff: ignore[suspicious-pickle-import]
import re
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal

import entitysdk
from entitysdk import models
from entitysdk.types import AssetLabel, ContentType, Sex
from pydantic import Discriminator, Field, StringConstraints, model_validator

from obi_one.core.block import Block
from obi_one.core.exception import ConfigValidationError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.blocks.ion_channel_equations.ion_channel_equations import (
    EquationKey,
    equation_schema_extra,
)
from obi_one.scientific.from_id.brain_region_from_id import BrainRegionFromID
from obi_one.scientific.from_id.ion_channel_recording_from_id import IonChannelRecordingFromID
from obi_one.scientific.from_id.species_from_id import SpeciesFromID
from obi_one.scientific.from_id.strain_from_id import StrainFromID
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig
from obi_one.utils.process import run_and_log

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
    "from obi_one.scientific.tasks.ion_channel_modeling import plot_fitted_model\n"
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


NEURON_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"


def neuron_safe_name(name: str) -> str:
    """A channel name as a NEURON SUFFIX: Kv6.2 gives Kv6_2."""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", name)
    return safe if re.match(r"[A-Za-z_]", safe) else f"_{safe}"


def _id(entity: Any) -> uuid.UUID | None:
    return entity.id if entity is not None else None


def _shared(items: list, what: str, key: Callable = _id, label: Callable = str) -> Any:
    distinct = {key(item): item for item in items}
    if len(distinct) > 1:
        values = ", ".join(sorted(label(item) for item in distinct.values()))
        msg = f"The recordings differ in {what} ({values}), so set the model's {what}."
        raise ConfigValidationError(msg)
    return next(iter(distinct.values()))


def _ancestors(region_id: uuid.UUID, db_client: entitysdk.client.Client) -> list:
    chain = [db_client.get_entity(entity_id=region_id, entity_type=models.BrainRegion)]
    while chain[-1].parent_structure_id:
        chain.append(
            db_client.get_entity(
                entity_id=chain[-1].parent_structure_id, entity_type=models.BrainRegion
            )
        )
    return chain


def common_parent_region(regions: list, db_client: entitysdk.client.Client) -> Any:
    """The deepest region that contains every one of the regions."""
    region_ids = list(dict.fromkeys(region.id for region in regions))
    if len(region_ids) == 1:
        return regions[0]
    chains = [_ancestors(region_id, db_client) for region_id in region_ids]
    in_all = set.intersection(*({region.id for region in chain} for chain in chains))
    for region in chains[0]:
        if region.id in in_all:
            return region
    msg = "The recordings' brain regions have no common parent, so set the model's brain region."
    raise ConfigValidationError(msg)


def generic_subject(species: Any, strain: Any, db_client: entitysdk.client.Client) -> Any:
    """The `Generic <species>[/<strain>]` subject, registered in the project when there is none."""
    name = f"Generic {species.name}" + (f"/{strain.name}" if strain else "")
    for subject in db_client.search_entity(entity_type=models.Subject, query={"name": name}):
        if subject.species.id == species.id and _id(subject.strain) == _id(strain):
            return subject
    return db_client.register_entity(
        models.Subject(
            name=name,
            description=f"Subject for models of {species.name} built from several subjects.",
            sex=Sex.unknown,
            species=species,
            strain=strain,
        )
    )


@dataclass(frozen=True)
class ResolvedModelProperties:
    ion_channel_name: str
    temperature: float | None
    species: Any
    strain: Any
    brain_region: Any
    # The recordings' own subject, when they share one with this species and strain.
    subject: Any


class IonChannelModelProperties(Block):
    """What the fitted model is registered with. An unset property comes from the recordings."""

    ion_channel_name: Annotated[str, StringConstraints(pattern=NEURON_NAME_PATTERN)] | None = Field(
        default=None,
        title="Ion channel name",
        description=(
            "SUFFIX of the mod file. Unset: the recordings' channel, so Kv6.2 gives Kv6_2. "
            "Must start with a letter or underscore, and contain only letters, numbers and "
            "underscores."
        ),
    )
    temperature: float | None = Field(
        default=None,
        title="Temperature",
        description="Temperature of the model, in °C. Unset: the recordings' temperature.",
    )
    species: SpeciesFromID | None = Field(
        default=None,
        title="Species",
        description="Species of the model. Unset: the recordings' species.",
    )
    strain: StrainFromID | None = Field(
        default=None,
        title="Strain",
        description=(
            "Strain of the model, of its species. Unset: the strain of the recordings of that "
            "species, if any."
        ),
    )
    brain_region: BrainRegionFromID | None = Field(
        default=None,
        title="Brain region",
        description=(
            "Brain region of the model. Unset: the deepest region containing all the "
            "recordings' regions."
        ),
    )


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    MODEL = "Model"


class HodgkinHuxleyIonChannelModel(Block):
    """The channel model to fit: one equation per gating variable, plus their exponents."""

    title: ClassVar[str] = "Hodgkin-Huxley ion channel model"

    m_power: Annotated[int, Field(ge=1, le=4)] | list[Annotated[int, Field(ge=1, le=4)]] = Field(
        title="m exponent in channel equation",
        default=1,
        description=(
            r"Exponent \(p\) of \(m\) in the channel equation: "
            r"\(g = \bar{g} \cdot m^p \cdot h^q\)"
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    h_power: Annotated[int, Field(ge=0, le=4)] | list[Annotated[int, Field(ge=0, le=4)]] = Field(
        title="h exponent in channel equation",
        default=1,
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
        json_schema_extra=equation_schema_extra,
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
        json_schema_extra=equation_schema_extra,
    )

    hinf_eq: Literal[EquationKey.SIG_FIT_HINF] = Field(
        title="h∞ equation",
        description=(
            r"Steady state inactivation parameter \(h_{\infty}\) equation. "
            r"This equation will be used for solving the differential equation: "
            r"\( \frac{dh}{dt} = \frac{h_{\infty} - h}{\tau_{h}} \)"
        ),
        default=EquationKey.SIG_FIT_HINF,
        json_schema_extra=equation_schema_extra,
    )

    htau_eq: Literal[EquationKey.SIG_FIT_HTAU] = Field(
        title="h time constant equation",
        description=(
            r"Inactivation time constant \(\tau_h\) equation. "
            r"This equation will be used for solving the differential equation: "
            r"\( \frac{dh}{dt} = \frac{h_{\infty} - h}{\tau_{h}} \)"
        ),
        default=EquationKey.SIG_FIT_HTAU,
        json_schema_extra=equation_schema_extra,
    )


# One member, but a discriminated union rather than a bare block: the editor draws it as a
# block_union, so a second channel formalism becomes another member and nothing else changes.
IonChannelModelUnion = Annotated[HodgkinHuxleyIonChannelModel, Discriminator("type")]


class IonChannelFittingScanConfig(InfoScanConfig):
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

        model_properties: IonChannelModelProperties = Field(
            default=IonChannelModelProperties(),
            title="Model properties",
            description=(
                "The channel name, temperature, species, strain and brain region the model is "
                "registered with. Each defaults to the recordings' value; set it when they "
                "differ, or to change it."
            ),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.ION_CHANNEL_MODEL_PROPERTIES},
        )

        @model_validator(mode="before")
        @classmethod
        def move_ion_channel_name(cls, data: Any) -> Any:
            """Configs from before model_properties name the channel at the top level."""
            if isinstance(data, dict) and "ion_channel_name" in data:
                data = dict(data)
                properties = dict(data.get("model_properties") or {})
                properties.setdefault("ion_channel_name", data.pop("ion_channel_name"))
                data["model_properties"] = properties
            return data

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

    def input_entities(self, db_client: entitysdk.client.Client) -> list:
        entities = [
            recording.entity(db_client=db_client) for recording in self.initialize.recordings
        ]
        # Fails at generation, before anything is registered, when a property can't be resolved.
        self.resolve_model_properties(entities, db_client=db_client)
        return entities

    def resolve_model_properties(
        self, recordings: list, db_client: entitysdk.client.Client
    ) -> ResolvedModelProperties:
        given = self.initialize.model_properties

        ion_channel_name = given.ion_channel_name or neuron_safe_name(
            _shared(
                [recording.ion_channel for recording in recordings],
                "ion channel",
                label=lambda channel: channel.name,
            ).name
        )
        temperature = (
            given.temperature
            if given.temperature is not None
            else _shared(
                [recording.temperature for recording in recordings],
                "temperature",
                key=lambda temperature: temperature,
                label=lambda temperature: "none" if temperature is None else f"{temperature} °C",
            )
        )
        species: Any = (
            given.species.entity(db_client=db_client)
            if given.species
            else _shared(
                [recording.subject.species for recording in recordings],
                "species",
                label=lambda species: species.name,
            )
        )
        if given.strain:
            strain = given.strain.entity(db_client=db_client)
        else:
            strains = [
                recording.subject.strain
                for recording in recordings
                if recording.subject.species.id == species.id
            ]
            strain = (
                _shared(
                    strains,
                    "strain",
                    label=lambda strain: strain.name if strain else "no strain",
                )
                if strains
                else None
            )
        if strain and strain.species_id != species.id:  # ty:ignore[unresolved-attribute]
            msg = f"Strain {strain.name} is not a strain of {species.name}."  # ty:ignore[unresolved-attribute]
            raise ConfigValidationError(msg)
        brain_region = (
            given.brain_region.entity(db_client=db_client)
            if given.brain_region
            else common_parent_region(
                [recording.brain_region for recording in recordings], db_client=db_client
            )
        )

        subjects = {recording.subject.id: recording.subject for recording in recordings}
        subject = next(iter(subjects.values())) if len(subjects) == 1 else None
        if subject and (subject.species.id != species.id or _id(subject.strain) != _id(strain)):
            subject = None

        return ResolvedModelProperties(
            ion_channel_name=ion_channel_name,
            temperature=temperature,
            species=species,
            strain=strain,
            brain_region=brain_region,
            subject=subject,
        )


class IonChannelFittingSingleConfig(IonChannelFittingScanConfig, SingleConfigMixin):
    """Only allows single values and ensures nested attributes follow the same rule."""


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
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
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
        properties: ResolvedModelProperties,
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

        recording_names = ", ".join(
            str(recording.entity(db_client=db_client).name) for recording in self.recordings
        )

        subject = properties.subject or generic_subject(
            properties.species, properties.strain, db_client=db_client
        )

        model = db_client.register_entity(
            entitysdk.models.IonChannelModel(  # ty:ignore[possibly-missing-submodule]
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
            eq_names: dict[str, str] = {
                "minf": model.minf_eq,
                "mtau": model.mtau_eq,
                "hinf": model.hinf_eq,
                "htau": model.htau_eq,
            }
            # run ion_channel_builder main function to get optimised parameters
            eq_popt = extract_all_equations(
                data_paths=trace_paths,
                ljps=trace_ljps,
                eq_names=eq_names,  # ty:ignore[invalid-argument-type]
                voltage_exclusion=VOLTAGE_EXCLUSION,
                stim_timings=STIM_TIMINGS,
                stim_timings_corrections=STIM_TIMINGS_CORRECTIONS,
                output_folder=self.config.coordinate_output_root,
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
                ion="k",
                m_power=model.m_power,  # ty:ignore[invalid-argument-type]
                h_power=model.h_power,  # ty:ignore[invalid-argument-type]
                output_name=output_name,  # ty:ignore[invalid-argument-type]
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
                mech_current="ik",
                temperature=properties.temperature,
                mech_conductance_name=self.conductance_name(mech_suffix),
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

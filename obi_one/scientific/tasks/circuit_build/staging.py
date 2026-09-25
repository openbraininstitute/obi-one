"""Staging: download MEModel components and translate the config into an ADS spec."""

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, cast

from entitysdk.client import Client
from entitysdk.downloaders.memodel import download_memodel
from entitysdk.models import MEModel
from entitysdk.schemas.memodel import DownloadedMEModel

from obi_one.core.exception import OBIONEError
from obi_one.scientific.blocks.synaptic_models.base import SynapticModelBase
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram.block import (
    ExcitatoryTsodyksMarkramSynapticModel,
    InhibitoryTsodyksMarkramSynapticModel,
)

if TYPE_CHECKING:
    from obi_one.scientific.tasks.circuit_build.config import (
        OrganoidCircuitBuildSingleConfig,
    )

L = logging.getLogger(__name__)

# Synapse mechanism name -> obi-one synaptic model providing its .mod file.
SYNAPSE_MODEL_CLASSES: dict[str, type[SynapticModelBase]] = {
    "ProbAMPANMDA_EMS": ExcitatoryTsodyksMarkramSynapticModel,
    "ProbGABAAB_EMS": InhibitoryTsodyksMarkramSynapticModel,
}

# Synapse mechanism name -> bundled catalogue reference in sonata-builder.
SYNAPSE_MODEL_REFS = {
    "ProbAMPANMDA_EMS": "obi_reference.ProbAMPANMDA_EMS.v1",
    "ProbGABAAB_EMS": "obi_reference.ProbGABAAB_EMS.v1",
}

_CELL_CLASS_TO_SYNAPSE_CLASS = {
    "excitatory": "EXC",
    "inhibitory": "INH",
    "modulatory": "MOD",
}


def memodel_ref(memodel_id: str) -> str:
    """Catalogue reference for a MEModel entity."""
    return f"entitycore.memodel.{memodel_id}"


def _extract_hoc_template_name(hoc_file: Path) -> str:
    """Extract the template name from a HOC file ('begintemplate' statement)."""
    content = hoc_file.read_text(encoding="utf-8")
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    content = re.sub(r"//.*$", "", content, flags=re.MULTILINE)
    match = re.search(r"\bbegintemplate\s+\"?(\w+)\"?", content)
    if match is None:
        msg = f"No 'begintemplate' statement found in HOC file {hoc_file}"
        raise OBIONEError(msg)
    return match.group(1)


def _catalogue_record(
    ref: str,
    population_cell_class: str,
    species: str,
    downloaded: DownloadedMEModel,
    component_source_dir: Path,
    memodel: MEModel,
) -> dict[str, object]:
    """Build a sonata-builder catalogue record for one staged MEModel."""
    record: dict[str, object] = {
        "model_catalog_id": ref,
        "version": "1",
        "model_kind": "biophysical",
        "species": species,
        "cell_class": population_cell_class,
        "hoc_template_name": _extract_hoc_template_name(downloaded.hoc_path),
        "hoc_path": str(downloaded.hoc_path.relative_to(component_source_dir)),
        "morphology_path": str(downloaded.morphology_path.relative_to(component_source_dir)),
        "mechanism_paths": [
            str((downloaded.mechanisms_dir / mech_file).relative_to(component_source_dir))
            for mech_file in downloaded.mechanism_files
        ],
        "redistribution_allowed": False,
        "source_url": f"entitycore://memodel/{memodel.id}",
        "validation_status": "unverified",
        "supported_export_profiles": ["neurodamus_biophysical_v1"],
    }
    calibration = memodel.calibration_result
    if calibration is not None:
        record["dynamics_params"] = {
            "threshold_current": calibration.threshold_current,
            "holding_current": calibration.holding_current,
        }
    if memodel.mtypes:
        record["mtype"] = memodel.mtypes[0].pref_label
    if memodel.emodel.etypes:
        record["etype"] = memodel.emodel.etypes[0].pref_label
    return record


def stage_components(
    config: "OrganoidCircuitBuildSingleConfig",
    db_client: Client,
    component_source_dir: Path,
) -> dict[str, str]:
    """Download all MEModel components and write the build catalogue.

    Creates under ``component_source_dir``:
      - ``components/memodels/<id>/{hoc,morphology,mechanisms}/`` per MEModel entity
      - ``components/synapses/*.mod`` for the Tsodyks-Markram synapse models
      - ``catalogues/entitycore_models.json`` mapping ``entitycore.memodel.<id>`` refs
        to the downloaded files

    Args:
        config: The single build configuration.
        db_client: entitysdk client.
        component_source_dir: Root directory the catalogue paths are relative to.

    Returns:
        Dict mapping population name -> model_ref.
    """
    components_dir = component_source_dir / "components"
    records: dict[str, dict] = {}
    population_refs: dict[str, str] = {}

    for name, population in config.populations.items():
        memodel = cast("MEModel", population.memodel.entity(db_client=db_client))
        ref = memodel_ref(str(memodel.id))
        population_refs[name] = ref

        if ref in records:
            continue

        dest = components_dir / "memodels" / str(memodel.id)
        downloaded = download_memodel(db_client, memodel=memodel, output_dir=dest, max_concurrent=4)
        records[ref] = _catalogue_record(
            ref,
            population.cell_class,
            config.experiment.species,
            downloaded,
            component_source_dir,
            memodel,
        )
        L.info("Staged MEModel %s for population '%s'", memodel.id, name)

    synapse_dir = components_dir / "synapses"
    synapse_dir.mkdir(parents=True, exist_ok=True)
    for synapse_model in sorted({r.synapse_model for r in config.connectivity_rules.values()}):
        SYNAPSE_MODEL_CLASSES[synapse_model].copy_mod_files(synapse_dir)

    catalogue = {
        "catalogue_version": "0.1.0",
        "catalogue_id": "entitycore",
        "models": records,
    }
    catalogue_path = component_source_dir / "catalogues" / "entitycore_models.json"
    catalogue_path.parent.mkdir(parents=True, exist_ok=True)
    catalogue_path.write_text(json.dumps(catalogue, indent=2), encoding="utf-8")

    return population_refs


def build_ads_dict(
    config: "OrganoidCircuitBuildSingleConfig",
    population_refs: dict[str, str],
    catalogue_path: str,
) -> dict:
    """Translate a single config into an ADS (Assembloid Design Specification) dict.

    Args:
        config: The single build configuration.
        population_refs: Population name -> model_ref from staging.
        catalogue_path: Path to the staged catalogue JSON (added to model_references).

    Returns:
        ADS dictionary ready for ``sonata_builder.DesignSpec``.
    """
    experiment = config.experiment
    geometry = config.geometry

    geometry_dict: dict = {
        "kind": geometry.shape,
        "radius_um": geometry.radius_um,
        "centre_um": [0.0, 0.0, 0.0],
        "placement": {
            "method": "poisson_disc",
            "min_distance_um": geometry.min_soma_distance_um,
        },
    }
    if geometry.shape == "disc":
        geometry_dict["thickness_um"] = geometry.thickness_um
    if geometry.shape == "sphere_on_substrate":
        geometry_dict["substrate_z_um"] = 0.0

    populations = [
        {
            "name": name,
            "fraction": population.fraction,
            "cell_class": population.cell_class,
            "synapse_class": _CELL_CLASS_TO_SYNAPSE_CLASS[population.cell_class],
            "model_ref": population_refs[name],
            "evidence": {
                "evidence_level": population.evidence_level,
                "parameter_status": "template_default",
                "source": "obi_one_form",
                "rationale": "Population prior entered in the OBI-ONE circuit build form.",
            },
        }
        for name, population in config.populations.items()
    ]

    rules = []
    for rule_name, rule in config.connectivity_rules.items():
        rules.append(
            {
                "rule_id": rule_name,
                "connection_kind": "chemical",
                "edge_granularity": "synapse",
                "source_population": rule.source_population.block_name,
                "target_population": rule.target_population.block_name,
                "generator": "distance_class_pair",
                "probability": {
                    "kernel": "exponential",
                    "p_max": rule.p_max,
                    "lambda_um": rule.lambda_um,
                },
                "synapses_per_connected_pair": {
                    "distribution": "zero_truncated_poisson",
                    "mean": rule.synapses_per_pair_mean,
                },
                "synapse": {
                    "model_ref": SYNAPSE_MODEL_REFS[rule.synapse_model],
                    "conductance_nS": {
                        "distribution": "lognormal",
                        "mean": rule.conductance_mean_ns,
                        "std": rule.conductance_std_ns,
                        "min": 0.1,
                    },
                    "decay_time_ms": {
                        "distribution": "normal_clipped",
                        "mean": rule.decay_time_mean_ms,
                        "std": rule.decay_time_std_ms,
                        "min": 1.0,
                    },
                    "u_syn": {
                        "distribution": "uniform",
                        "min": rule.u_syn_min,
                        "max": rule.u_syn_max,
                    },
                    "delay_ms": {
                        "distribution": "distance_linear",
                        "base": rule.delay_base_ms,
                        "per_um": rule.delay_per_um_ms,
                    },
                    "depression_time_ms": rule.depression_time_ms,
                    "facilitation_time_ms": rule.facilitation_time_ms,
                    "n_rrp_vesicles": 1,
                },
                "placement": {
                    "target_sections": list(rule.target_sections),
                    "mode": "uniform_by_length",
                },
                "allow_autapses": rule.allow_autapses,
                "evidence": {
                    "evidence_level": rule.evidence_level,
                    "parameter_status": "user_fixed",
                    "source": "obi_one_form",
                    "rationale": "Connectivity prior entered in the OBI-ONE circuit build form.",
                },
            }
        )

    return {
        "schema_version": "0.1.0",
        "spec_id": f"obi_one.{config.campaign_name}",
        "experiment": {
            "experiment_id": f"obi_one_{config.campaign_name}",
            "preparation": experiment.preparation,
            "days_in_vitro": experiment.days_in_vitro,
            "species": experiment.species,
            "cell_source": experiment.cell_source,
        },
        "coordinate_system": {
            "coordinate_frame_id": "global_um_rhs_v1",
            "unit": "um",
        },
        "geometry": geometry_dict,
        "orientation": {"method": geometry.orientation},
        "total_cells": config.initialize.total_cells,
        "populations": populations,
        "connectivity": {"seed": config.initialize.seed, "rules": rules},
        "model_references": {"catalogues": [catalogue_path]},
        "export": {
            "profile_id": "neurodamus_biophysical_v1",
            "include_simulation_config": True,
        },
        "randomness": {"root_seed": config.initialize.seed},
        "metadata": {
            "created_by": "obi_one.circuit_build",
            "campaign_name": config.campaign_name,
        },
    }

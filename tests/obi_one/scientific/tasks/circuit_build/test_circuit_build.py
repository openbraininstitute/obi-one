"""Tests for the organoid circuit build task config and ADS translation."""

import pytest
from pydantic import ValidationError

from obi_one.core.exception import OBIONEError
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.tasks.circuit_build.config import (
    OrganoidCircuitBuildSingleConfig,
    PopulationReference,
)
from obi_one.scientific.tasks.circuit_build.staging import build_ads_dict, memodel_ref

DUMMY_MEMODEL_A = "00000000-0000-0000-0000-000000000001"
DUMMY_MEMODEL_B = "00000000-0000-0000-0000-000000000002"


def _population(memodel_id: str, cell_class: str, fraction: float) -> dict:
    return {
        "fraction": fraction,
        "cell_class": cell_class,
        "memodel": MEModelFromID(id_str=memodel_id),
    }


def _rule(source: str, target: str) -> dict:
    return {
        "source_population": PopulationReference(block_dict_name="populations", block_name=source),
        "target_population": PopulationReference(block_dict_name="populations", block_name=target),
        "p_max": 0.15,
        "lambda_um": 100.0,
        "synapse_model": "ProbAMPANMDA_EMS",
    }


def _make_config(**overrides) -> OrganoidCircuitBuildSingleConfig:
    kwargs = {
        "info": {
            "campaign_name": "test_campaign",
            "campaign_description": "test",
        },
        "initialize": {"total_cells": 20, "seed": 7},
        "registration": {
            "register_in_entitycore": False,
            "subject_name": "subject",
            "brain_region_name": "region",
            "brain_region_hierarchy_name": "hierarchy",
        },
        "populations": {
            "exc": _population(DUMMY_MEMODEL_A, "excitatory", 0.8),
            "inh": _population(DUMMY_MEMODEL_B, "inhibitory", 0.2),
        },
        "connectivity_rules": {"exc_to_exc": _rule("exc", "exc")},
    }
    kwargs.update(overrides)
    return OrganoidCircuitBuildSingleConfig(**kwargs)


class TestConfigValidation:
    def test_valid_config(self):
        config = _make_config()
        assert config.initialize.total_cells == 20

    def test_fractions_must_sum_to_one(self):
        with pytest.raises(OBIONEError, match=r"sum to 1\.0"):
            _make_config(
                populations={
                    "exc": _population(DUMMY_MEMODEL_A, "excitatory", 0.5),
                }
            )

    def test_at_least_one_population(self):
        with pytest.raises(OBIONEError, match="At least one population"):
            _make_config(populations={}, connectivity_rules={})

    def test_rule_must_reference_existing_population(self):
        # Block reference resolution rejects unknown population names
        with pytest.raises(ValidationError, match="not found in 'populations'"):
            _make_config(connectivity_rules={"bad": _rule("exc", "ghost")})


class TestAdsTranslation:
    def test_build_ads_dict(self):
        config = _make_config()
        refs = {name: memodel_ref(DUMMY_MEMODEL_A) for name in config.populations}
        ads = build_ads_dict(config, refs, "catalogues/test.json")

        assert ads["total_cells"] == 20
        assert ads["randomness"]["root_seed"] == 7
        assert ads["experiment"]["preparation"] == "organoid_3d"
        assert ads["model_references"]["catalogues"] == ["catalogues/test.json"]

        pops = {p["name"]: p for p in ads["populations"]}
        assert pops["exc"]["fraction"] == pytest.approx(0.8)
        assert pops["exc"]["synapse_class"] == "EXC"
        assert pops["inh"]["synapse_class"] == "INH"
        assert pops["exc"]["model_ref"] == memodel_ref(DUMMY_MEMODEL_A)

        rule = ads["connectivity"]["rules"][0]
        assert rule["rule_id"] == "exc_to_exc"
        assert rule["source_population"] == "exc"
        assert rule["probability"]["kernel"] == "exponential"
        assert rule["synapse"]["model_ref"] == "obi_reference.ProbAMPANMDA_EMS.v1"
        assert rule["placement"]["target_sections"] == ["soma", "basal", "apical"]

    def test_ads_is_valid_against_sonata_builder_schema(self):
        sonata_builder = pytest.importorskip("sonata_builder")
        config = _make_config()
        refs = {name: memodel_ref(DUMMY_MEMODEL_A) for name in config.populations}
        ads = build_ads_dict(config, refs, "catalogues/test.json")

        spec = sonata_builder.DesignSpec(**ads)
        resolved = spec.resolve()
        assert resolved.spec.total_cells == 20

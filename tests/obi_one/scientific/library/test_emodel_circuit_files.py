"""Tests for reading mechanism variables from a circuit's hoc and mod files.

The golden file holds what the endpoint returned for ``hoc:cADpyr_L6BPC`` through the
``emodel_circuit`` derivation and the EModel entity (captured from a staging run). The
same template's hoc and mod files live in the sample circuit under ``examples/``.
"""

import json
import math
from pathlib import Path
from typing import NamedTuple

import pytest

from obi_one.scientific.library.emodel_circuit_files import (
    HocTemplateError,
    mechanism_variables,
    read_hoc_biophysics,
    read_mod_mechanism,
)
from obi_one.scientific.library.memodel_circuit import (
    _build_mechanism_variables_by_ion_channel_response,
)

CIRCUIT_DIR = Path("examples/data/single_neuron_circuits/SingleNeuronCircuit__top_nodes_dim6__IDX1")
HOC_PATH = CIRCUIT_DIR / "emodels_hoc" / "cADpyr_L6BPC.hoc"
GOLDEN_PATH = Path(__file__).parent / "data" / "manipulation_properties_cADpyr_L6BPC_from_db.json"


class Location(NamedTuple):
    """``section_params`` entry the BluePyOpt template iterates over."""

    name: str
    value: str


class Distribution(NamedTuple):
    """``range_params`` entry the BluePyOpt template iterates over."""

    location: str
    param_name: str
    value: str


# The EModel metadata lists this STATE variable of CaDynamics_DC0 as if it were RANGE.
# The mod file does not declare it in RANGE, so the files cannot produce it.
KNOWN_DB_ONLY_VARIABLES = {"CaDynamics_DC0": {"cai_CaDynamics_DC0"}}


def _model_from_files(hoc_text: str):
    biophysics = read_hoc_biophysics(hoc_text)
    mechanisms = {
        channel: read_mod_mechanism((CIRCUIT_DIR / "mod" / f"{channel}.mod").read_text())
        for channel in biophysics.inserted_mechanisms - {"pas"}
    }
    return biophysics, mechanisms


@pytest.fixture(scope="module")
def from_files() -> dict:
    biophysics, mechanisms = _model_from_files(HOC_PATH.read_text())
    assert biophysics.warnings == []
    variables, mapping = mechanism_variables(biophysics, mechanisms)
    response = _build_mechanism_variables_by_ion_channel_response(variables, mapping)
    return {channel: entry.model_dump() for channel, entry in response.items()}


@pytest.fixture(scope="module")
def from_db() -> dict:
    return json.loads(GOLDEN_PATH.read_text())


class TestGoldenAgainstDatabaseResponse:
    def test_same_channels(self, from_files, from_db):
        assert set(from_files) == set(from_db)

    def test_same_section_lists_per_channel(self, from_files, from_db):
        for channel, golden in from_db.items():
            assert sorted(from_files[channel]["section_lists"]) == sorted(
                golden["section_lists"]
            ), channel

    def test_same_variables_per_channel(self, from_files, from_db):
        for channel, golden in from_db.items():
            expected = set(golden["variables"]) - KNOWN_DB_ONLY_VARIABLES.get(channel, set())
            assert set(from_files[channel]["variables"]) == expected, channel

    def test_same_limits_and_variable_type(self, from_files, from_db):
        for channel, golden in from_db.items():
            for name, detail in golden["variables"].items():
                if name in KNOWN_DB_ONLY_VARIABLES.get(channel, set()):
                    continue
                ours = from_files[channel]["variables"][name]
                assert ours["limits"] == detail["limits"], name
                assert ours["variable_type"] == detail["variable_type"], name

    def test_every_database_value_is_reproduced(self, from_files, from_db):
        """Every non-null value the database returned is read from the hoc file.

        Where the database had null, the hoc file may hold the real value, which is
        the only difference allowed.
        """
        for channel, golden in from_db.items():
            for name, detail in golden["variables"].items():
                if name in KNOWN_DB_ONLY_VARIABLES.get(channel, set()):
                    continue
                ours = from_files[channel]["variables"][name]["section_lists_original_values"]
                theirs = detail["section_lists_original_values"]
                assert set(ours) == set(theirs), name
                for section_list, value in theirs.items():
                    if value is None:
                        continue
                    assert ours[section_list] is not None, (name, section_list)
                    assert math.isclose(ours[section_list], value, rel_tol=1e-12), (
                        name,
                        section_list,
                    )

    def test_units_come_from_the_mod_parameter_block(self, from_files):
        natg = from_files["NaTg"]["variables"]
        assert natg["gNaTgbar_NaTg"]["units"] == "S/cm2"
        assert natg["vshifth_NaTg"]["units"] == "mV"
        assert not natg["slopeh_NaTg"]["units"]

    def test_distance_distributed_values_use_the_scale_factor(self, from_files):
        ih = from_files["Ih"]["variables"]["gIhbar_Ih"]["section_lists_original_values"]
        assert ih == {
            "apical": 1.151226556055784e-05,
            "basal": 1.151226556055784e-05,
            "somatic": 1.151226556055784e-05,
        }

    def test_entity_ids_are_unknown_from_files(self, from_files):
        assert all(entry["entity_id"] is None for entry in from_files.values())


class TestRoundTripThroughTheRealTemplate:
    """Render a hoc file with BluePyEModel's own template, then read it back."""

    def test_reader_recovers_what_the_template_was_given(self):
        jinja2 = pytest.importorskip("jinja2")
        bluepyemodel = pytest.importorskip("bluepyemodel")
        templates = Path(bluepyemodel.__file__).parent / "export_emodel" / "templates"
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(templates), autoescape=False)
        channels = {"all": ["pas"], "somatic": ["NaTg", "SK_E2"], "apical": ["Ih"]}

        hoc_text = env.get_template("cell_template_neurodamus_sbo.jinja2").render(
            template_name="RoundTrip",
            channels=channels,
            section_params=[
                ("all", [Location("g_pas", "3.4e-05")]),
                ("somatic", [Location("gNaTgbar_NaTg", "0.088"), Location("cm", "1")]),
            ],
            range_params=[
                Distribution(
                    "apical", "gIhbar_Ih", "(-0.8696 + 2.087*exp((%.17g)*0.0031))*1.15e-05"
                )
            ],
        )
        biophysics = read_hoc_biophysics(hoc_text)

        assert biophysics.channels_by_section_list == channels
        assert biophysics.assignments == {
            ("all", "g_pas"): 3.4e-05,
            ("somatic", "gNaTgbar_NaTg"): 0.088,
            ("somatic", "cm"): 1.0,
        }
        assert biophysics.distributions == {("apical", "gIhbar_Ih"): 1.15e-05}


class TestHocReaderIsFailClosed:
    def test_unknown_line_in_biophys_raises(self):
        broken = HOC_PATH.read_text().replace("    Ra = 100\n", "    Ra = 100 * scale\n")
        with pytest.raises(HocTemplateError, match="unexpected line in biophys"):
            read_hoc_biophysics(broken)

    def test_unknown_line_in_insert_channel_raises(self):
        broken = HOC_PATH.read_text().replace("    insert pas\n", "    if (x) insert pas\n")
        with pytest.raises(HocTemplateError, match="unexpected line in insertChannel"):
            read_hoc_biophysics(broken)

    def test_quoted_line_is_truncated(self):
        long_line = "x" * 10_000
        broken = HOC_PATH.read_text().replace("    Ra = 100\n", f"    {long_line}\n")
        with pytest.raises(HocTemplateError) as excinfo:
            read_hoc_biophysics(broken)
        assert len(str(excinfo.value)) < 200

    def test_missing_procedure_raises(self):
        with pytest.raises(HocTemplateError, match="proc insertChannel"):
            read_hoc_biophysics("proc biophys() {\n}\n")

    def test_distribution_without_a_lone_factor_gives_null_and_a_warning(self):
        hoc_text = (
            "proc insertChannel() {\n  forsec this.apical {\n    insert Ih\n  }\n}\n"
            "proc biophys() {\n"
            '  distribute_distance(CellRef.apical, "gIhbar_Ih", "exp(%.17g)/(1+2)")\n'
            "}\n"
        )
        result = read_hoc_biophysics(hoc_text)
        assert result.distributions == {("apical", "gIhbar_Ih"): None}
        assert len(result.warnings) == 1

    def test_missing_mod_file_raises(self):
        biophysics = read_hoc_biophysics(HOC_PATH.read_text())
        with pytest.raises(HocTemplateError, match="no mod file for inserted mechanisms"):
            mechanism_variables(biophysics, {})


class TestModReader:
    def test_reads_suffix_range_and_units(self):
        mechanism = read_mod_mechanism((CIRCUIT_DIR / "mod" / "NaTg.mod").read_text())
        assert mechanism.suffix == "NaTg"
        assert mechanism.range_variables == [
            "gNaTgbar",
            "gNaTg",
            "ina",
            "vshifth",
            "vshiftm",
            "slopeh",
            "slopem",
        ]
        assert mechanism.global_variables == []
        assert mechanism.units["gNaTgbar"] == "S/cm2"
        assert mechanism.units["vshifth"] == "mV"
        assert "slopeh" not in mechanism.units

    def test_reads_global_variables(self):
        mechanism = read_mod_mechanism(
            "NEURON {\n  SUFFIX demo\n  RANGE gbar, i\n  GLOBAL q10, shift\n}\n"
            "PARAMETER {\n  gbar = 0.1 (S/cm2)\n  q10 = 2.3\n}\n"
        )
        assert mechanism.global_variables == ["q10", "shift"]

    def test_missing_neuron_block_raises(self):
        with pytest.raises(HocTemplateError, match="no NEURON block"):
            read_mod_mechanism("PARAMETER {\n  g = 1\n}\n")


class TestReaderRejectsMalformedFiles:
    def test_mod_without_suffix_raises(self):
        with pytest.raises(HocTemplateError, match="no SUFFIX"):
            read_mod_mechanism("NEURON {\n  RANGE g\n}\n")

    def test_unbalanced_procedure_raises(self):
        with pytest.raises(HocTemplateError, match="unbalanced braces"):
            read_hoc_biophysics("proc insertChannel() {\n  forsec this.all {\n")

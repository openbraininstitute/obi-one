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
    ModMechanism,
    _distribution_value,
    mechanism_variables,
    read_hoc_biophysics,
    read_mod_mechanism,
)
from obi_one.scientific.library.emodel_parameters import (
    ChannelInfo,
    ChannelSectionListMapping,
    MechanismVariable,
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

    def test_leading_factor_is_a_coefficient_not_the_value(self):
        hoc_text = (
            "proc insertChannel() {\n  forsec this.apical {\n    insert Ih\n  }\n}\n"
            "proc biophys() {\n"
            '  distribute_distance(CellRef.apical, "gIhbar_Ih", "2.087*exp(%.17g)+0.5")\n'
            "}\n"
        )
        result = read_hoc_biophysics(hoc_text)
        assert result.distributions == {("apical", "gIhbar_Ih"): None}
        assert len(result.warnings) == 1

    def test_value_written_first_is_read_like_the_derivation_path(self):
        """Real line of rCA1-like ``cADpyr_bin_4``: BluePyEModel's ``step`` distribution."""
        hoc_text = (
            "proc insertChannel() {\n  forsec this.apical {\n    insert Ca_LVAst\n  }\n}\n"
            "proc biophys() {\n"
            '  distribute_distance(CellRef.apical, "gCa_LVAstbar_Ca_LVAst", '
            '"0.0039788257139893729 * (0.1 + 0.9 * int((%.17g > 370.67452392578127) '
            '&& (%.17g < 519.34097900390623)))")\n'
            "}\n"
        )
        result = read_hoc_biophysics(hoc_text)
        assert result.distributions == {("apical", "gCa_LVAstbar_Ca_LVAst"): 0.0039788257139893729}
        assert result.warnings == []

    def test_missing_mod_file_raises(self):
        biophysics = read_hoc_biophysics(HOC_PATH.read_text())
        with pytest.raises(HocTemplateError, match="no mod file for inserted mechanisms"):
            mechanism_variables(biophysics, {})


class TestBuiltInMechanisms:
    HOC_TEXT = (
        'check_parameter("celsius", 34, celsius)\n'
        'check_parameter("q10_demo", 2.3, q10_demo)\n'
        "proc insertChannel() {\n"
        "  forsec this.somatic {\n    insert hh\n    insert extracellular\n"
        "    insert na_ion\n    insert capacitance\n    insert demo\n  }\n"
        "}\n"
        "proc biophys() {\n"
        "  forsec CellRef.somatic {\n    gnabar_hh = 0.12\n    ena = 50\n"
        "    xg_extracellular = 1e9\n    gbar_demo = 0.5\n  }\n"
        "}\n"
    )
    DEMO_MOD = ModMechanism(suffix="demo", range_variables=["gbar"], global_variables=["q10"])

    def test_only_mechanisms_with_a_mod_file_need_one(self):
        biophysics = read_hoc_biophysics(self.HOC_TEXT)
        assert biophysics.inserted_mechanisms == {"hh", "extracellular", "demo"}
        assert biophysics.mod_file_mechanisms == {"demo"}

    def test_built_ins_get_their_neuron_variables_and_ions_are_skipped(self):
        biophysics = read_hoc_biophysics(self.HOC_TEXT)
        variables, mapping = mechanism_variables(biophysics, {"demo": self.DEMO_MOD})
        by_name = {(v.neuron_variable, v.section_list): v for v in variables}
        assert by_name["gnabar_hh", "somatic"].value == pytest.approx(0.12)
        assert by_name["gnabar_hh", "somatic"].units == "S/cm2"
        assert by_name["gnabar_hh", "somatic"].limits == [0.0, 10.0]
        assert by_name["el_hh", "somatic"].value is None
        assert by_name["xg_extracellular", "somatic"].value == pytest.approx(1e9)
        assert set(mapping.channel_to_section_lists) == {"hh", "extracellular", "demo"}

    def test_global_value_comes_from_check_simulator(self):
        biophysics = read_hoc_biophysics(self.HOC_TEXT)
        assert biophysics.global_values == {"celsius": 34.0, "q10_demo": 2.3}
        variables, _ = mechanism_variables(biophysics, {"demo": self.DEMO_MOD})
        q10 = next(v for v in variables if v.neuron_variable == "q10_demo")
        assert q10.variable_type == "GLOBAL"
        assert q10.value == pytest.approx(2.3)


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

    def test_statements_on_one_line_and_comments(self):
        mechanism = read_mod_mechanism(
            "NEURON { SUFFIX demo RANGE a, b GLOBAL c USEION na READ ena WRITE ina\n"
            "  NONSPECIFIC_CURRENT i : RANGE not_a_variable\n}\n"
        )
        assert mechanism.suffix == "demo"
        assert mechanism.range_variables == ["a", "b"]
        assert mechanism.global_variables == ["c"]

    def test_units_come_from_parameter_or_assigned(self):
        """rCA1's ``cagk.mod`` declares ``tau`` and ``gkca`` with units in ASSIGNED only."""
        mechanism = read_mod_mechanism(
            "NEURON {\n  SUFFIX cagk\n  RANGE gbar, gkca, tau, st\n}\n"
            "PARAMETER {\n  gbar=.01 (mho/cm2) : max\n  st=1 (1)\n}\n"
            "ASSIGNED {\n  ik (mA/cm2)\n  oinf\n  tau (ms)\n  gkca (mho/cm2)\n}\n"
        )
        assert mechanism.units == {
            "gbar": "mho/cm2",
            "st": "1",
            "ik": "mA/cm2",
            "tau": "ms",
            "gkca": "mho/cm2",
        }

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


D = "%.17g"


class TestDistributionValue:
    """The ``{value}`` of every BluePyEModel distribution, as BluePyOpt prints it in hoc."""

    @pytest.mark.parametrize(
        ("formula", "value"),
        [
            pytest.param(f"(-0.8696 + 2.087*exp(({D})*0.0031))*0.0012", 0.0012, id="exp"),
            pytest.param(f"exp((-{D})/50)*0.04", 0.04, id="exp_na_dend"),
            pytest.param(f"(1. + 3./100. * {D})*2.5e-05", 2.5e-05, id="linear_hd_apic"),
            pytest.param(f"(15./(1. + exp((300-{D})/50)))*0.012", 0.012, id="sigmoid_kad_apic"),
            pytest.param(
                f"0.0039788257139893729 * (0.1 + 0.9 * int(({D} > 370.67) && ({D} < 519.34)))",
                0.0039788257139893729,
                id="step",
            ),
            pytest.param(
                f"(-68.802204816706208-5*{D}/150)", -68.802204816706208, id="linear_e_pas_apic"
            ),
            pytest.param(f"(70.5+5*{D}/150)", 70.5, id="linear_e_pas_apic_positive"),
            pytest.param(f"(0.5 + 1.2 * exp({D} * -0.003)) * 0.07", 0.07, id="custom_product"),
            pytest.param("0.031", 0.031, id="uniform"),
            pytest.param(f"(1+{D})*-0.5", -0.5, id="negative_value"),
            pytest.param(f"exp(-{D}/50)*1.5e-05", 1.5e-05, id="exponent_in_value"),
        ],
    )
    def test_value_is_found(self, formula, value):
        assert _distribution_value(formula) == value

    @pytest.mark.parametrize(
        "formula",
        [
            pytest.param(f"2.087*exp({D})+0.5", id="number_added_after_a_function"),
            pytest.param(f"0.5*{D}*0.2", id="two_plain_number_factors"),
            pytest.param(f"(1 + 2*exp({D}*3)*0.5)", id="sum_with_a_function"),
            pytest.param(f"{D}/150", id="no_plain_number"),
            pytest.param(f"0.5*(1+2)*{D}", id="factor_not_depending_on_distance"),
            pytest.param(f"(-0.8696 + 2.087*exp({D}*0.0031))", id="distribution_without_value"),
            pytest.param("x", id="not_a_number"),
            pytest.param(f"(0.5*{D}", id="unbalanced_parenthesis"),
        ],
    )
    def test_no_single_reading_gives_none(self, formula):
        assert _distribution_value(formula) is None


class TestModUnits:
    def test_repeated_blocks_are_merged(self):
        """``StochKv3.mod`` has two ASSIGNED blocks; units of the first were lost."""
        mechanism = read_mod_mechanism(
            "NEURON {\n  SUFFIX StochKv3\n  RANGE gk, an, N0L0\n}\n"
            "ASSIGNED {\n  an (/ms)\n  gk (S/cm2)\n}\n"
            "ASSIGNED {\n  N0L0 N1L0 : populations\n}\n"
        )
        assert mechanism.units == {"an": "/ms", "gk": "S/cm2"}

    def test_state_units_are_read(self):
        mechanism = read_mod_mechanism(
            "NEURON {\n  SUFFIX CaDynamics_DC0\n  RANGE decay\n}\n"
            "PARAMETER {\n  decay = 80 (ms)\n}\n"
            "STATE {\n  cai (mM)\n}\n"
        )
        assert mechanism.units == {"decay": "ms", "cai": "mM"}

    def test_comments_are_ignored(self):
        """A COMMENT block can quote a whole block; ``:`` comments can hide a name."""
        mechanism = read_mod_mechanism(
            "COMMENT\n  Old version:\n  NEURON {\n    SUFFIX old\n    RANGE stale\n  }\n"
            "  PARAMETER {\n    stale = 2 (mV)\n  }\nENDCOMMENT\n"
            "NEURON {\n  SUFFIX new : was old\n  RANGE g : , hidden\n}\n"
            "PARAMETER {\n  g = 1 (S/cm2) : not (mV)\n}\n"
        )
        assert mechanism.suffix == "new"
        assert mechanism.range_variables == ["g"]
        assert mechanism.units == {"g": "S/cm2"}

    def test_several_names_on_one_line_and_parameter_wins(self):
        mechanism = read_mod_mechanism(
            "NEURON {\n  SUFFIX demo\n}\n"
            "PARAMETER {\n  gbar = 0.1 (S/cm2) <0, 1e9>\n}\n"
            "ASSIGNED {\n  ina (mA/cm2) ik (mA/cm2)\n  gbar (mho/cm2)\n}\n"
        )
        assert mechanism.units == {"gbar": "S/cm2", "ina": "mA/cm2", "ik": "mA/cm2"}

    def test_repo_stochkv3_keeps_every_unit(self):
        mechanism = read_mod_mechanism((CIRCUIT_DIR / "mod" / "StochKv3.mod").read_text())
        assert {k: mechanism.units[k] for k in ("an", "gk", "ltau", "gkbar")} == {
            "an": "/ms",
            "gk": "S/cm2",
            "ltau": "ms",
            "gkbar": "S/cm2",
        }


class TestSectionListOrder:
    def test_section_lists_are_sorted_and_values_kept(self):
        variables = [
            MechanismVariable(
                neuron_variable="cm",
                section_list=section,
                value=value,
                channel_name="-",
                variable_type="RANGE",
            )
            for section, value in (
                ("somatic", 1.0),
                ("axonal", 2.0),
                ("basal", 3.0),
                ("apical", 4.0),
            )
        ]
        mapping = ChannelSectionListMapping(
            channel_to_section_lists={
                "NaTg": ChannelInfo(section_lists=["somatic", "axonal"], entity_id=None),
                "Ih": ChannelInfo(section_lists=["basal", "apical"], entity_id=None),
            }
        )
        response = _build_mechanism_variables_by_ion_channel_response(variables, mapping)
        assert response["-"].section_lists == ["apical", "axonal", "basal", "somatic"]
        assert response["-"].variables["cm"].section_lists_original_values == {
            "somatic": 1.0,
            "axonal": 2.0,
            "basal": 3.0,
            "apical": 4.0,
        }

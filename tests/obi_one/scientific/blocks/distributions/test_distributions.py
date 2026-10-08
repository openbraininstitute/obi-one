import math

import numpy as np
import pytest
from bluepyemodel.preprocessing.distributions import resolve_distance_dependent_distribution
from bluepyemodel.preprocessing.schemas import (
    STANDARD_DISTANCE_DEPENDENT_DISTRIBUTIONS,
    LinearHDPasDistanceDependentDistribution,
)

import obi_one as obi
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.blocks import (
    check_distance_function,
    validate_safe_distance_function,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.config import (
    EModelOptimizationScanConfig,
)


def _optimization_config(**overrides):
    config_data = {
        "info": {"campaign_name": "test", "campaign_description": "test"},
        "initialize": {
            "emodel": "test",
            "etype": {"id_str": "etype"},
        },
        "target_efeatures": {"task_result": {"id_str": "target"}},
        "morphology": {"cell_morphology": {"id_str": "morphology"}},
        "parameters_selection": {
            "ion_channel_models": [{"id_str": "icm"}],
            "mechanism_regions": {"somatic": [{"ion_channel_model": {"id_str": "icm"}}]},
        },
    }
    config_data.update(overrides)
    return EModelOptimizationScanConfig.model_validate(config_data)


class TestDistanceDependentDistributions:
    @pytest.mark.parametrize(
        ("distribution_class", "expected_name", "expected_function"),
        [
            (obi.UniformDistanceDependentDistribution, "uniform", None),
            (
                obi.ExponentialDistanceDependentDistribution,
                "exp",
                "(-0.8696 + 2.087*math.exp(({distance})*0.0031))*{value}",
            ),
            (
                obi.StepDistanceDependentDistribution,
                "step",
                (
                    "{value} * (0.1 + 0.9 * float(({distance} > {step_begin}) & "
                    "({distance} < {step_end})))"
                ),
            ),
            (
                obi.ExponentialNaDendDistanceDependentDistribution,
                "exp_na_dend",
                "math.exp((-{distance})/50.)*{value}",
            ),
            (
                obi.LinearHDApicDistanceDependentDistribution,
                "linear_hd_apic",
                "(1. + 3./100. * {distance})*{value}",
            ),
            (
                obi.SigmoidKADApicDistanceDependentDistribution,
                "sigmoid_kad_apic",
                "(15./(1. + math.exp((300.-{distance})/50.)))*{value}",
            ),
            (
                obi.LinearEPasApicDistanceDependentDistribution,
                "linear_e_pas_apic",
                "({value}-5.*{distance}/150.)",
            ),
            (
                obi.SigmoidKADDistanceDependentDistribution,
                "sigmoid_kad",
                "(15./(1. + math.exp((150.-{distance})/10.)))*{value}",
            ),
            (
                obi.SigmoidKDBMApicDistanceDependentDistribution,
                "sigmoid_kdbm_apic",
                "(15./(1. + math.exp(({distance}-50.)/50.)))*{value}",
            ),
        ],
    )
    def test_legacy_distributions_serialize(
        self, distribution_class, expected_name, expected_function
    ):
        distribution = distribution_class()

        assert distribution.to_emc_dict() == {
            "name": expected_name,
            "function": expected_function,
            "soma_ref_location": 0.5,
        }

    def test_custom_distribution_is_validated_and_serialized(self):
        distribution = obi.CustomDistanceDependentDistribution(
            function="({value} + {distance}) / 2.0",
            soma_ref_location=0.25,
        )

        assert distribution.to_emc_dict(name="custom_profile") == {
            "name": "custom_profile",
            "function": "({value} + {distance}) / 2.0",
            "soma_ref_location": 0.25,
        }

    def test_custom_distribution_serializes_parameters(self):
        distribution = obi.CustomDistanceDependentDistribution(
            function="math.exp({distance}*{constant})*{value}",
            parameters=["constant"],
        )

        assert distribution.to_emc_dict(name="decay") == {
            "name": "decay",
            "function": "math.exp({distance}*{constant})*{value}",
            "soma_ref_location": 0.5,
            "parameters": ["constant"],
        }

    def test_empty_distribution_parameters_are_not_serialized(self):
        distribution = obi.CustomDistanceDependentDistribution(
            function="({value} + {distance}) / 2.0",
            parameters=[],
        )

        assert "parameters" not in distribution.to_emc_dict(name="custom_profile")

    def test_distribution_parameter_names_are_not_scan_dimensions(self):
        distribution = obi.CustomDistanceDependentDistribution(
            function="math.exp({distance}*{constant})*{value}",
            parameters=["constant"],
        )

        assert distribution.parameters == ("constant",)
        assert distribution.multiple_value_parameters(category_name="distributions") == []

    def test_custom_distribution_requires_value_and_distance(self):
        with pytest.raises(ValueError, match=r"\{value\} placeholder"):
            obi.CustomDistanceDependentDistribution(function="{distance}")

        with pytest.raises(ValueError, match=r"\{distance\} placeholder"):
            obi.CustomDistanceDependentDistribution(function="{value}")

    def test_custom_distribution_requires_declared_parameters(self):
        with pytest.raises(ValueError, match=r"\{constant\} placeholder"):
            obi.CustomDistanceDependentDistribution(
                function="math.exp({distance})*{value}",
                parameters=["constant"],
            )

    def test_distribution_parameters_require_a_function(self):
        with pytest.raises(ValueError, match="must define a function"):
            obi.DistanceDependentDistribution(parameters=["constant"])

    def test_standard_distributions_are_available_without_declaration(self):
        """The ten legacy distributions are selectable by name without being declared."""
        assert set(STANDARD_DISTANCE_DEPENDENT_DISTRIBUTIONS) == {
            "uniform",
            "exp",
            "step",
            "exp_na_dend",
            "linear_hd_apic",
            "sigmoid_kad_apic",
            "linear_e_pas_apic",
            "linear_hdpas",
            "sigmoid_kad",
            "sigmoid_kdbm_apic",
        }
        assert isinstance(
            resolve_distance_dependent_distribution("linear_hdpas", {}),
            LinearHDPasDistanceDependentDistribution,
        )

    def test_custom_distribution_declared_on_the_config_deserializes(self):
        config = _optimization_config(
            distance_dependent_distributions={
                "mouse_decay": {
                    "type": "CustomDistanceDependentDistribution",
                    "function": "math.exp({distance})*{value}",
                },
            }
        )

        assert isinstance(
            config.distance_dependent_distributions["mouse_decay"],
            obi.CustomDistanceDependentDistribution,
        )

    def test_optimization_parameter_selection_has_no_declared_distributions_by_default(self):
        config = _optimization_config()

        assert dict(config.distance_dependent_distributions) == {}

    def test_step_distribution_preserves_morphology_derived_placeholders(self):
        """BluePyEModel computes step_begin/step_end from the morphology hot-spot.

        They must not be required as user-declared ``parameters`` and must be
        preserved verbatim in the function string for BluePyEModel to substitute
        at runtime via ``get_hotspot_location()``.
        """
        distribution = obi.StepDistanceDependentDistribution()

        assert "{step_begin}" in distribution.function
        assert "{step_end}" in distribution.function
        assert distribution.parameters is None
        assert distribution.to_emc_dict() == {
            "name": "step",
            "function": (
                "{value} * (0.1 + 0.9 * float(({distance} > {step_begin}) & "
                "({distance} < {step_end})))"
            ),
            "soma_ref_location": 0.5,
        }


class TestDistanceFunctionSafety:
    """The distance function reaches BluePyEModel's eval(); it must be AST-restricted."""

    @pytest.mark.parametrize(
        "unsafe_function",
        [
            "__import__('os').system('id') + {value} + {distance}",
            "os.system('rm -rf /') + {value}*{distance}",
            "open('/etc/passwd').read() + {value} + {distance}",
            "(lambda: 1)() + {value} + {distance}",
            "({value}).__class__.__mro__[1] + {distance}",
            "{value}[0] + {distance}",
            "eval('1') + {value} + {distance}",
        ],
    )
    def test_unsafe_custom_distribution_is_rejected(self, unsafe_function):
        with pytest.raises(ValueError, match="Distance function"):
            obi.CustomDistanceDependentDistribution(function=unsafe_function)

    @pytest.mark.parametrize(
        "safe_function",
        [
            "({value} + {distance}) / 2.0",
            "math.exp((-{distance})/50.)*{value}",
            "float({distance} > 100.) * {value}",
            "(15./(1. + math.exp((300.-{distance})/50.)))*{value}",
            "{value} * (0.1 + 0.9 * float(({distance} > 10.) & ({distance} < 20.)))",
        ],
    )
    def test_safe_custom_distribution_is_accepted(self, safe_function):
        distribution = obi.CustomDistanceDependentDistribution(function=safe_function)
        assert distribution.function == safe_function

    @pytest.mark.parametrize(
        "unsafe_function",
        [
            "int({distance}) + {value}",
            "int({value}) ** int({distance})",
            "math.factorial(30) + {value} + {distance}",
            "math.comb(40, 20) + {value} + {distance}",
            "math.floor({distance}) + {value}",
        ],
    )
    def test_int_producing_calls_are_rejected(self, unsafe_function):
        """int() and int-returning math functions are forbidden (unbounded-integer DoS)."""
        with pytest.raises(ValueError, match="Distance function"):
            obi.CustomDistanceDependentDistribution(function=unsafe_function)

    def test_overly_complex_function_is_rejected(self):
        """A structurally large expression (under the length cap) is rejected by the node cap."""
        long_function = "{value}" + "+{distance}" * 30
        with pytest.raises(ValueError, match="too complex"):
            obi.CustomDistanceDependentDistribution(function=long_function)

    def test_integer_literals_are_rejected(self):
        """Integer literals are forbidden (arbitrary-precision); users must write floats."""
        with pytest.raises(ValueError, match="must be floats"):
            obi.CustomDistanceDependentDistribution(function="{value}*{distance} + 3")

    def test_power_operator_is_rejected(self):
        """`**` is forbidden: integer exponentiation is an unbounded-memory DoS."""
        with pytest.raises(ValueError, match="Pow"):
            obi.CustomDistanceDependentDistribution(function="{value} ** {distance}")

    def test_overly_long_function_is_rejected(self):
        """A giant raw string is rejected before parsing (bounds parse-time cost)."""
        long_function = "{value}+{distance}+" + "9." * 300
        # The field-level ``max_length`` constraint rejects it (Pydantic message).
        with pytest.raises(ValueError, match="at most 500 characters"):
            obi.CustomDistanceDependentDistribution(function=long_function)

    def test_check_distance_function_reports_valid(self):
        result = check_distance_function("math.exp((-{distance})/50.)*{value}")
        assert result.valid
        assert result.error is None

    def test_check_distance_function_reports_error_span(self):
        fn = "os.system('x') + {value} + {distance}"
        result = check_distance_function(fn)
        assert not result.valid
        # The span points at the offending call in the original string.
        assert fn[result.from_ : result.to] == "os.system('x')"
        assert "calls are limited" in result.error

    def test_check_distance_function_flags_int_literal_position(self):
        fn = "{value}*{distance} + 3"
        result = check_distance_function(fn)
        assert not result.valid
        assert fn[result.from_ : result.to] == "3"

    def test_check_distance_function_accepts_declared_parameters(self):
        result = check_distance_function(
            "math.exp({distance}*{constant})*{value}", parameters=("constant",)
        )
        assert result.valid

    def test_check_distance_function_flags_disallowed_name(self):
        # Covers the disallowed-name leaf branch via the structured checker.
        result = check_distance_function("foo + {value} + {distance}")
        assert not result.valid
        assert "disallowed name" in result.error

    def test_check_distance_function_rejects_too_long(self):
        result = check_distance_function("{value}+{distance}+" + "1.0+" * 300)
        assert not result.valid
        assert "too long" in result.error
        assert result.to == len("{value}+{distance}+" + "1.0+" * 300)

    def test_check_distance_function_reports_syntax_error(self):
        result = check_distance_function("({value} + {distance}")
        assert not result.valid
        assert "valid expression" in result.error

    def test_check_distance_function_requires_value_and_distance(self):
        missing_value = check_distance_function("{distance} * 2.0")
        assert not missing_value.valid
        assert "{value}" in missing_value.error

        missing_distance = check_distance_function("{value} * 2.0")
        assert not missing_distance.valid
        assert "{distance}" in missing_distance.error

    def test_check_distance_function_flags_undeclared_placeholder(self):
        result = check_distance_function("{value} + {distance} + {mystery}")
        assert not result.valid
        assert "undeclared placeholders" in result.error
        assert "mystery" in result.error

    def test_check_distance_function_rejects_too_complex(self):
        # Covers the node-cap branch of the structured checker (under the length cap).
        result = check_distance_function("{value}" + "+{distance}" * 30)
        assert not result.valid
        assert "too complex" in result.error

    def test_check_distance_function_allows_math_call(self):
        # A valid math.* call exercises the safe-call path.
        result = check_distance_function("math.exp({distance}) * {value}")
        assert result.valid
        assert result.error is None

    def test_check_distance_function_rejects_keyword_arguments(self):
        # Covers the keyword-arguments rejection branch in call validation.
        result = check_distance_function("math.exp({distance}, base=2.0) * {value}")
        assert not result.valid
        assert "keyword arguments" in result.error

    def test_check_distance_function_rejects_non_math_attribute(self):
        # Covers the attribute-access branch (attribute on something other than math).
        result = check_distance_function("({value}).real + {distance}")
        assert not result.valid
        assert "attributes may only be accessed on the math module" in result.error

    def test_check_distance_function_rejects_string_constants(self):
        # String constants + % enable allocation bombs, e.g. '%10000000s' % x. Reject all strings.
        for fn in (
            '"%10000000s" % ({value} + {distance})',
            '"x" + {value} + {distance}',
        ):
            result = check_distance_function(fn)
            assert not result.valid, fn
            assert "literals must be floats" in result.error

    def test_check_distance_function_rejects_math_introspection(self):
        # math.__dict__/__loader__ etc. are introspection escapes; only allowed attrs pass.
        for fn in (
            "math.__dict__ + {value} + {distance}",
            "math.__loader__ + {value} + {distance}",
        ):
            result = check_distance_function(fn)
            assert not result.valid, fn
            assert "is not an allowed attribute" in result.error

    def test_check_distance_function_allows_math_constant(self):
        result = check_distance_function("math.pi * {value} * {distance} * 0.0 + {value}")
        assert result.valid

    def test_validate_safe_distance_function_raises_on_too_long(self):
        with pytest.raises(ValueError, match="too long"):
            validate_safe_distance_function("{value}+{distance}+" + "1.0+" * 300)

    def test_validate_safe_distance_function_raises_on_syntax_error(self):
        with pytest.raises(ValueError, match="valid expression"):
            validate_safe_distance_function("({value} + {distance}")

    def test_check_distance_function_accepts_step_runtime_placeholders(self):
        # step_begin/step_end are morphology-derived runtime placeholders, always allowed.
        result = check_distance_function(
            "{value} * (0.1 + 0.9 * float(({distance} > {step_begin}) & ({distance} < {step_end})))"
        )
        assert result.valid

    @pytest.mark.parametrize(
        "unsafe_function",
        [
            # Comment channel: the payload after '#' is lexed away before the AST, and its
            # format spec survives the placeholder regex, so bluepyopt's str.format pads a
            # string to gigabytes (memory-exhaustion DoS). Comments are rejected outright.
            "{value}*{distance} # {value:>999999999}",
            "{value}*{distance}  # any comment",
            # Format spec / conversion / attribute / index / positional / empty brace fields
            # are not bare-identifier placeholders and are rejected before parsing.
            "{value}*{distance}*{value:>9}",
            "{value}*{distance}*{value!r}",
            "{value}*{distance}*{value.__class__}",
            "{value}*{distance}*{value[0]}",
            "{value}*{distance}*{0}",
            "{value}*{distance}*{}",
            "{value}*{distance}*{a.b}",
        ],
    )
    def test_comment_and_format_spec_channels_are_rejected(self, unsafe_function):
        """The distance function must not smuggle format specs via comments or brace fields."""
        with pytest.raises(ValueError, match="Distance function"):
            obi.CustomDistanceDependentDistribution(function=unsafe_function)

    def test_check_distance_function_flags_comment_position(self):
        fn = "{value}*{distance} # {value:>999999999}"
        result = check_distance_function(fn)
        assert not result.valid
        assert "comments are not allowed" in result.error
        assert fn[result.from_] == "#"

    def test_check_distance_function_flags_format_spec_span(self):
        fn = "{value}*{distance}*{value:>9}"
        result = check_distance_function(fn)
        assert not result.valid
        assert "invalid placeholder" in result.error
        assert fn[result.from_ : result.to] == "{value:>9}"

    def test_check_distance_function_flags_unbalanced_open_brace(self):
        fn = "{value}*{distance}*{scale"
        result = check_distance_function(fn)
        assert not result.valid
        assert "unbalanced '{'" in result.error

    def test_check_distance_function_flags_unbalanced_close_brace(self):
        fn = "{value}*{distance}}"
        result = check_distance_function(fn)
        assert not result.valid
        assert "unbalanced '}'" in result.error

    @pytest.mark.parametrize(
        "unsafe_function", ["{value}*{distance}*{scale", "{value}*{distance}}"]
    )
    def test_unbalanced_braces_are_rejected(self, unsafe_function):
        with pytest.raises(ValueError, match="unbalanced"):
            obi.CustomDistanceDependentDistribution(function=unsafe_function)

    def test_unsafe_distribution_config_rejects_comment_dos(self):
        """The comment/format-spec DoS must block config creation, not just the block."""
        with pytest.raises(ValueError, match="Distance function"):
            _optimization_config(
                distance_dependent_distributions={
                    "dos": {
                        "type": "CustomDistanceDependentDistribution",
                        "function": "{value}*{distance} # {value:>999999999}",
                    },
                }
            )

    def test_unsafe_distribution_rejected_when_building_a_config(self):
        """An unsafe custom distribution must block EModelOptimizationScanConfig creation."""
        with pytest.raises(ValueError, match="Distance function"):
            _optimization_config(
                distance_dependent_distributions={
                    "pwned": {
                        "type": "CustomDistanceDependentDistribution",
                        "function": "__import__('os').system('id') + {value} + {distance}",
                    },
                }
            )

    def test_safe_distribution_accepted_when_building_a_config(self):
        config = _optimization_config(
            distance_dependent_distributions={
                "decay": {
                    "type": "CustomDistanceDependentDistribution",
                    "function": "math.exp((-{distance})/50.)*{value}",
                },
            }
        )
        assert isinstance(
            config.distance_dependent_distributions["decay"],
            obi.CustomDistanceDependentDistribution,
        )


class TestFloatConstantDistribution:
    def test_sample_returns_repeated_scalar_values(self):
        """FloatConstantDistribution.sample() returns repeated scalar values, not nested lists."""
        dist = obi.FloatConstantDistribution(value=5.0)
        samples = dist.sample(n=3)
        assert samples == [5.0, 5.0, 5.0]
        assert all(isinstance(s, float) for s in samples)

    def test_sample_with_explicit_rng(self):
        """Passing an explicit numpy Generator to sample() works and is honored."""
        dist = obi.FloatConstantDistribution(value=math.pi)
        rng = np.random.default_rng(42)
        samples = dist.sample(n=2, rng=rng)
        assert samples == [math.pi, math.pi]

    def test_sample_is_concrete_and_usable(self):
        """Distribution.sample() is concrete and usable through subclasses."""
        dist = obi.FloatConstantDistribution(value=1.5)
        # Should not raise NotImplementedError
        result = dist.sample(n=1)
        assert result == [1.5]


class TestExponentialDistribution:
    def test_sample_returns_positive_float_samples(self):
        """ExponentialDistribution.sample() returns positive float samples."""
        dist = obi.ExponentialDistribution(scale=10.0, random_seed=42)
        samples = dist.sample(n=10)
        assert len(samples) == 10
        assert all(isinstance(s, float) for s in samples)
        assert all(s > 0 for s in samples)

    def test_sample_with_explicit_rng(self):
        """Passing an explicit numpy Generator to sample() works and is honored."""
        dist = obi.ExponentialDistribution(scale=5.0)
        rng = np.random.default_rng(123)
        samples1 = dist.sample(n=3, rng=rng)
        rng = np.random.default_rng(123)  # Reset seed
        samples2 = dist.sample(n=3, rng=rng)
        assert samples1 == samples2

    def test_sample_is_concrete_and_usable(self):
        """Distribution.sample() is concrete and usable through subclasses."""
        dist = obi.ExponentialDistribution(scale=1.0, random_seed=1)
        result = dist.sample(n=1)
        assert len(result) == 1
        assert isinstance(result[0], float)
        assert result[0] > 0

    def test_exponential_distribution_shift(self):
        dist = obi.ExponentialDistribution(scale=1.0, shift=5.0, random_seed=42)
        samples = dist.sample(10)

        assert all(sample >= 5.0 for sample in samples)

    def test_exponential_distribution_shift_adds_constant(self):
        base = obi.ExponentialDistribution(scale=1.0, random_seed=42)
        shifted = obi.ExponentialDistribution(scale=1.0, shift=5.0, random_seed=42)

        base_samples = base.sample(5)
        shifted_samples = shifted.sample(5)

        assert shifted_samples == [sample + 5.0 for sample in base_samples]


class TestGammaDistribution:
    def test_sample_returns_positive_float_samples(self):
        """GammaDistribution.sample() returns positive float samples."""
        dist = obi.GammaDistribution(shape=2.0, scale=5.0, random_seed=42)
        samples = dist.sample(n=10)
        assert len(samples) == 10
        assert all(isinstance(s, float) for s in samples)
        assert all(s > 0 for s in samples)

    def test_sample_with_explicit_rng(self):
        """Passing an explicit numpy Generator to sample() works and is honored."""
        dist = obi.GammaDistribution(shape=1.5, scale=2.0)
        rng = np.random.default_rng(456)
        samples1 = dist.sample(n=3, rng=rng)
        rng = np.random.default_rng(456)  # Reset seed
        samples2 = dist.sample(n=3, rng=rng)
        assert samples1 == samples2

    def test_sample_is_concrete_and_usable(self):
        """Distribution.sample() is concrete and usable through subclasses."""
        dist = obi.GammaDistribution(shape=1.0, scale=1.0, random_seed=1)
        result = dist.sample(n=1)
        assert len(result) == 1
        assert isinstance(result[0], float)
        assert result[0] > 0

    def test_gamma_distribution_shift(self):
        dist = obi.GammaDistribution(shape=2.0, scale=1.0, shift=5.0, random_seed=42)
        samples = dist.sample(10)

        assert all(sample >= 5.0 for sample in samples)


class TestDistributionConstraints:
    def test_constraint_validation_ge_gt(self):
        """Constraint validation raises for both ge and gt."""
        dist = obi.FloatConstantDistribution(value=1.0)
        with pytest.raises(ValueError, match="Only one of ge and gt can be specified"):
            dist.sample(n=1, ge=0.5, gt=0.5)

    def test_constraint_validation_le_lt(self):
        """Constraint validation raises for both le and lt."""
        dist = obi.FloatConstantDistribution(value=1.0)
        with pytest.raises(ValueError, match="Only one of le and lt can be specified"):
            dist.sample(n=1, le=2.0, lt=2.0)

    def test_constraint_validation_ge_le_inconsistent(self):
        """Constraint validation raises for ge > le."""
        dist = obi.FloatConstantDistribution(value=1.0)
        with pytest.raises(ValueError, match="ge must be less than or equal to le"):
            dist.sample(n=1, ge=2.0, le=1.0)

    def test_constraint_validation_gt_lt_inconsistent(self):
        """Constraint validation raises for gt >= lt."""
        dist = obi.FloatConstantDistribution(value=1.0)
        with pytest.raises(ValueError, match="gt must be less than lt"):
            dist.sample(n=1, gt=2.0, lt=2.0)

    def test_constraint_validation_ge_lt_inconsistent(self):
        """Constraint validation raises for ge > lt."""
        dist = obi.FloatConstantDistribution(value=1.0)
        with pytest.raises(ValueError, match="ge must be less than or equal to lt"):
            dist.sample(n=1, ge=2.0, lt=1.5)

    def test_constraint_validation_gt_le_inconsistent(self):
        """Constraint validation raises for gt >= le."""
        dist = obi.FloatConstantDistribution(value=1.0)
        with pytest.raises(ValueError, match="gt must be less than le"):
            dist.sample(n=1, gt=2.0, le=2.0)


class TestNormalDistribution:
    def test_sample_returns_float_samples(self):
        dist = obi.NormalDistribution(
            mean=0.0,
            standard_deviation=1.0,
            random_seed=42,
        )

        samples = dist.sample(n=10)

        assert len(samples) == 10
        assert all(isinstance(s, float) for s in samples)

    def test_sample_with_explicit_rng(self):
        dist = obi.NormalDistribution(
            mean=0.0,
            standard_deviation=1.0,
        )

        rng = np.random.default_rng(123)
        samples1 = dist.sample(n=3, rng=rng)

        rng = np.random.default_rng(123)
        samples2 = dist.sample(n=3, rng=rng)

        assert samples1 == samples2


class TestLogNormalDistribution:
    def test_sample_returns_positive_float_samples(self):
        dist = obi.LogNormalDistribution(
            mean=0.0,
            sigma=1.0,
            random_seed=42,
        )

        samples = dist.sample(n=10)

        assert len(samples) == 10
        assert all(isinstance(s, float) for s in samples)
        assert all(s > 0 for s in samples)

    def test_sample_with_explicit_rng(self):
        dist = obi.LogNormalDistribution(
            mean=0.0,
            sigma=1.0,
        )

        rng = np.random.default_rng(456)
        samples1 = dist.sample(n=3, rng=rng)

        rng = np.random.default_rng(456)
        samples2 = dist.sample(n=3, rng=rng)

        assert samples1 == samples2


class TestPoissonDistribution:
    def test_sample_returns_non_negative_integer_like_samples(self):
        dist = obi.PoissonDistribution(
            rate=5.0,
            random_seed=42,
        )

        samples = dist.sample(n=10)

        assert len(samples) == 10
        assert all(isinstance(s, float) for s in samples)
        assert all(s >= 0 for s in samples)
        assert all(float(s).is_integer() for s in samples)

    def test_sample_with_explicit_rng(self):
        dist = obi.PoissonDistribution(
            rate=5.0,
        )

        rng = np.random.default_rng(789)
        samples1 = dist.sample(n=3, rng=rng)

        rng = np.random.default_rng(789)
        samples2 = dist.sample(n=3, rng=rng)

        assert samples1 == samples2

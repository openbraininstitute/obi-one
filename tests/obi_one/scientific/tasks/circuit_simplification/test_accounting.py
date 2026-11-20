"""Tests for circuit-simplification accounting subtype mapping."""

import pytest
from obp_accounting_sdk.constants import ServiceSubtype

from obi_one.scientific.tasks.circuit_simplification.accounting import (
    service_subtype_for_algorithm,
    service_subtype_for_algorithm_block,
)
from obi_one.scientific.tasks.circuit_simplification.algorithms.models import (
    LifNestAlgorithm,
    NeatReductionAlgorithm,
    NeuronReduceAlgorithm,
    SingleCompartmentAlgorithm,
)


class TestServiceSubtypeForAlgorithm:
    def test_point_neuron_algorithms_are_small(self):
        assert (
            service_subtype_for_algorithm("lif_nest") == ServiceSubtype.CIRCUIT_SIMPLIFICATION_SMALL
        )

    def test_single_compartment_impedance_is_medium(self):
        assert (
            service_subtype_for_algorithm("single_compartment", filter_method="impedance")
            == ServiceSubtype.CIRCUIT_SIMPLIFICATION_MEDIUM
        )

    def test_single_compartment_timedomain_is_large(self):
        assert (
            service_subtype_for_algorithm("single_compartment", filter_method="timedomain")
            == ServiceSubtype.CIRCUIT_SIMPLIFICATION_LARGE
        )

    def test_neuron_reduce_is_medium(self):
        assert (
            service_subtype_for_algorithm("neuron_reduce")
            == ServiceSubtype.CIRCUIT_SIMPLIFICATION_MEDIUM
        )

    def test_neat_reduction_is_large(self):
        assert (
            service_subtype_for_algorithm("neat_reduction")
            == ServiceSubtype.CIRCUIT_SIMPLIFICATION_LARGE
        )

    def test_filter_algorithm_requires_filter_method(self):
        with pytest.raises(ValueError, match="requires filter_method"):
            service_subtype_for_algorithm("single_compartment")

    def test_unknown_algorithm_raises(self):
        with pytest.raises(ValueError, match="Unknown circuit simplification algorithm"):
            service_subtype_for_algorithm("not_an_algorithm")

    def test_unknown_filter_method_raises(self):
        with pytest.raises(ValueError, match="Unknown filter_method 'bogus'"):
            service_subtype_for_algorithm("single_compartment", filter_method="bogus")


class TestServiceSubtypeForAlgorithmBlock:
    def test_fixed_algorithm(self):
        assert (
            service_subtype_for_algorithm_block(LifNestAlgorithm())
            == ServiceSubtype.CIRCUIT_SIMPLIFICATION_SMALL
        )

    def test_neuron_reduce_is_medium(self):
        assert (
            service_subtype_for_algorithm_block(NeuronReduceAlgorithm())
            == ServiceSubtype.CIRCUIT_SIMPLIFICATION_MEDIUM
        )

    def test_neat_reduction_is_large(self):
        assert (
            service_subtype_for_algorithm_block(NeatReductionAlgorithm())
            == ServiceSubtype.CIRCUIT_SIMPLIFICATION_LARGE
        )

    @pytest.mark.parametrize(
        ("filter_method", "expected"),
        [
            ("impedance", ServiceSubtype.CIRCUIT_SIMPLIFICATION_MEDIUM),
            ("timedomain", ServiceSubtype.CIRCUIT_SIMPLIFICATION_LARGE),
        ],
    )
    def test_single_compartment_follows_filter_method(self, filter_method, expected):
        block = SingleCompartmentAlgorithm(filter_method=filter_method)
        assert service_subtype_for_algorithm_block(block) == expected

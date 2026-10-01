"""The discrete distribution's two arrays are one thing, and the UI now lets people edit it.

While both fields were hidden, only code built one of these, and only ever with matching
arrays. Each check below is a mistake a person can now make in the form, and every one of them
otherwise fails inside numpy with a message naming neither field.
"""

import numpy as np
import pytest
from pydantic import ValidationError

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.distributions.discrete import IntDiscreteDistribution


def test_it_samples_the_listed_values():
    drawn = IntDiscreteDistribution(
        values=(3, 7), probabilities=(0.5, 0.5)
    ).sample_with_constraints(200, rng=np.random.default_rng(0))

    assert set(drawn) == {3, 7}


def test_probabilities_need_not_sum_to_one():
    # They are normalized before sampling, which is why the UI shows each one's share.
    drawn = IntDiscreteDistribution(
        values=(1, 2), probabilities=(3.0, 1.0)
    ).sample_with_constraints(400, rng=np.random.default_rng(0))

    assert 0.6 < drawn.count(1) / len(drawn) < 0.9


@pytest.mark.parametrize(
    ("values", "probabilities"),
    [
        pytest.param((1, 2, 3), (0.5, 0.5), id="more values than probabilities"),
        pytest.param((1, 2), (0.4, 0.3, 0.3), id="more probabilities than values"),
        pytest.param((), (), id="no values at all"),
        pytest.param((1, 2), (-0.5, 1.5), id="a negative probability"),
        pytest.param((1, 2), (0.0, 0.0), id="every probability zero"),
    ],
)
def test_an_unusable_pair_is_rejected(values, probabilities):
    with pytest.raises(ValidationError):
        IntDiscreteDistribution(values=values, probabilities=probabilities)


def test_the_values_field_carries_the_table_element_and_is_shown():
    # Both fields used to be hidden, which left the block with nothing to edit but its seed.
    extra = IntDiscreteDistribution.model_fields["values"].json_schema_extra

    assert extra[SchemaKey.UI_ELEMENT] == UIElement.DISCRETE_PROBABILITIES
    assert not extra.get(SchemaKey.UI_HIDDEN)


def test_probabilities_stays_hidden_because_the_table_owns_it():
    # Rendered as its own list editor, it could be given a different length from `values` -
    # the one state the pair cannot be in.
    extra = IntDiscreteDistribution.model_fields["probabilities"].json_schema_extra

    assert extra[SchemaKey.UI_HIDDEN] is True


@pytest.mark.parametrize("field", ["values", "probabilities"])
def test_neither_array_is_sweepable(field):
    """A swept discrete distribution is a list of whole tuples.

    In the schema that is the same shape as a single tuple of values, so nothing downstream
    could tell "my five values" from "five separate configurations to run".
    """
    distribution = IntDiscreteDistribution(values=(1, 2), probabilities=(0.5, 0.5))

    assert "list" not in str(IntDiscreteDistribution.model_fields[field].annotation)
    assert distribution.multiple_value_parameters(category_name="distributions") == []

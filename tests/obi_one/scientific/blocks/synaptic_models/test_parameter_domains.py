"""Each built-in default must produce values its own parameter is allowed to take.

The domain is declared on the field, the default supplies that field, and nothing but this
test holds the two in agreement - which is why it draws rather than reasons: a Gamma or Normal
default is only wrong for its domain some of the time.
"""

import numpy as np
import pandas as pd

from obi_one.core.schema import SchemaKey
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram.block import (
    ExcitatoryTsodyksMarkramSynapticModel,
    TsodyksMarkramSynapticModel,
)
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram.domains import (
    ParameterDomain,
    is_valid_parameter_sample,
)


def _declared_domains():
    """Every domain declared on the model's fields, keyed by field name."""
    return {
        name: ParameterDomain(**field.json_schema_extra[SchemaKey.PARAMETER_DOMAIN])
        for name, field in TsodyksMarkramSynapticModel.model_fields.items()
        if isinstance(field.json_schema_extra, dict)
        and SchemaKey.PARAMETER_DOMAIN in field.json_schema_extra
    }


def test_every_sampled_parameter_declares_a_domain():
    # syn_type_id is the model's identity rather than a draw, so it has nothing to constrain.
    sampled = set(ExcitatoryTsodyksMarkramSynapticModel.parameter_names()) - {"syn_type_id"}

    assert len(_declared_domains()) == len(sampled)


def test_a_domain_says_what_it_expects():
    # The description is quoted back in the error a rejected draw raises, so an empty one
    # would produce "expected ; got [...]".
    for name, domain in _declared_domains().items():
        assert domain.description, name


def test_the_built_in_defaults_stay_inside_their_own_domains():
    # Drawn rather than reasoned about, and enough of them to catch a tail that falls outside.
    samples = ExcitatoryTsodyksMarkramSynapticModel().sample(
        pd.DataFrame(index=range(2000)), rng=np.random.default_rng(0)
    )
    parameters = [
        n for n in ExcitatoryTsodyksMarkramSynapticModel.parameter_names() if n != "syn_type_id"
    ]

    for parameter, domain in zip(parameters, _declared_domains().values(), strict=True):
        offending = [v for v in samples[parameter] if not is_valid_parameter_sample(v, domain)]
        assert offending == [], f"{parameter}: {offending[:3]} outside {domain.description}"

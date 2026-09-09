"""Each built-in default must produce values its own parameter is allowed to take.

The domain is declared on the field, the default supplies that field, and nothing but this
test holds the two in agreement - which is why it draws rather than reasons: a Gamma or Normal
default is only wrong for its domain some of the time.
"""

import numpy as np
import pandas as pd

from obi_one.scientific.blocks.synaptic_models.tsodyks_markram.block import (
    ExcitatoryTsodyksMarkramSynapticModel,
    TsodyksMarkramSynapticModel,
)
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram.domains import (
    is_valid_parameter_sample,
)


def test_every_sampled_parameter_declares_a_domain_and_a_default():
    fields = TsodyksMarkramSynapticModel._sampled_fields()

    # syn_type_id is the model's identity rather than a draw, so it declares neither.
    assert [p for p, _d in fields.values()] + ["syn_type_id"] == (
        ExcitatoryTsodyksMarkramSynapticModel.parameter_names()
    )
    assert set(fields) == set(TsodyksMarkramSynapticModel._default_distributions)


def test_a_domain_says_what_it_expects():
    # The description is quoted back in the error a rejected draw raises, so an empty one
    # would produce "expected ; got [...]".
    for field, (_parameter, domain) in TsodyksMarkramSynapticModel._sampled_fields().items():
        assert domain.description, field


def test_the_built_in_defaults_stay_inside_their_own_domains():
    # Drawn rather than reasoned about, and enough of them to catch a tail that falls outside.
    samples = ExcitatoryTsodyksMarkramSynapticModel().sample(
        pd.DataFrame(index=range(2000)), rng=np.random.default_rng(0)
    )

    for parameter, domain in TsodyksMarkramSynapticModel._sampled_fields().values():
        offending = [v for v in samples[parameter] if not is_valid_parameter_sample(v, domain)]
        assert offending == [], f"{parameter}: {offending[:3]} outside {domain.description}"

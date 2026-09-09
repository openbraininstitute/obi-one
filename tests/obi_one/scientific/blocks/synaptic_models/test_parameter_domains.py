"""Each built-in default must produce values its own parameter is allowed to take.

`domains.py` says what a parameter may be and `distributions.py` what it is when nobody
chooses; nothing but this test holds the two in agreement, which is why it draws rather than
reasons - a Gamma or Normal default is only wrong for its domain some of the time.
"""

import numpy as np
import pandas as pd

from obi_one.scientific.blocks.synaptic_models.tsodyks_markram.block import (
    ExcitatoryTsodyksMarkramSynapticModel,
)
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram.distributions import (
    _TSODYKS_MARKRAM_DEFAULTS,
)
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram.domains import (
    _TM_PARAMETER_DOMAINS,
    _is_valid_parameter_sample,
)


def test_every_parameter_with_a_default_has_a_domain():
    sampled = set(ExcitatoryTsodyksMarkramSynapticModel.parameter_names()) - {"syn_type_id"}

    assert sampled == set(_TM_PARAMETER_DOMAINS)


def test_there_is_a_default_for_every_domain():
    assert len(_TSODYKS_MARKRAM_DEFAULTS) == len(_TM_PARAMETER_DOMAINS)


def test_the_built_in_defaults_stay_inside_their_own_domains():
    # Drawn rather than reasoned about: a Gamma or Normal default is only wrong for its domain
    # some of the time, so this samples enough to catch a tail that falls outside.
    samples = ExcitatoryTsodyksMarkramSynapticModel().sample(
        pd.DataFrame(index=range(2000)), rng=np.random.default_rng(0)
    )

    for parameter, domain in _TM_PARAMETER_DOMAINS.items():
        offending = [v for v in samples[parameter] if not _is_valid_parameter_sample(v, domain)]
        assert offending == [], f"{parameter}: {offending[:3]} outside {domain.description}"

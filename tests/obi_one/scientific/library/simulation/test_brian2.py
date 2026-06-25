import numpy as np
import pytest

import obi_one.scientific.library.simulation.brian2.simulate_brian2 as test_module


@pytest.mark.parametrize("ids,times,expected",
                         [([1, 2, 3], [10., 20, 30], [False, False, False]),
                          ([1, 2, 3], [10.0, 20.0, 30.0], [False, False, False]),
                          ([1, 2, 1], [10.0, 11.0, 50.0], [False, False, False]),
                          ([1, 1, 2], [10.0, 20.0, 50.0], [False, False, False]),
                          ([1, 1], [10.0, 10.5], [False, True]),
                          ([2, 1, 1, 2], [5.0, 10.0, 11.0, 5.1], [False, False, True, True]),
                         ])
def test_get_close_spikes(ids, times, expected):
    np.testing.assert_array_equal(
        test_module._get_close_spikes(np.array(ids), np.array(times), 2.0),
        expected
        )

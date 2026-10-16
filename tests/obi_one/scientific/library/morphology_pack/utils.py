import morphio

from obi_one.scientific.library.morphology_pack.geometry import Morphology

# A soma of radius 5 at the origin with two neurites.
# - A dendrite along +x, 1 um in radius, with two traced points on its way to a fork at x = 20.
#   One branch runs 30 um along +y at half the radius, with a point 10 um in; the other is a
#   twig of 2 um.
# - An axon along -y, 0.5 um in radius, that bends 3 um aside at y = -100.
SWC = """\
1 1 0 0 0 5 -1
2 3 5 0 0 1 1
3 3 10 0 0 1 2
4 3 15 0 0 1 3
5 3 20 0 0 1 4
6 3 20 10 0 0.5 5
7 3 20 30 0 0.5 6
8 3 22 0 0 0.5 5
9 2 0 -5 0 0.5 1
10 2 0 -50 0 0.5 9
11 2 3 -100 0 0.5 10
12 2 0 -150 0 0.5 11
"""

AXON = 2
DENDRITE = 3


def load(text: str = SWC) -> Morphology:
    return Morphology.from_morphio(morphio.Morphology(text, "swc"))

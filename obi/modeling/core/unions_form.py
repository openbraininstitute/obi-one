from obi.modeling.core.unions import subclass_union

from typing import Union, Type
from obi.modeling.core.form import Form

from obi.modeling.simulation.simulations import *

FormUnion = subclass_union(Form)
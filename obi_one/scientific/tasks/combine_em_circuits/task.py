from obi_one.core.task import Task
from obi_one.scientific.tasks.combine_em_circuits.config import CombineEMCircuitsSingleConfig

class CombineEMCircuitsTask(Task):

    config: CombineEMCircuitsSingleConfig

    def execute():
        pass
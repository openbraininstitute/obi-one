from obi_one.core.form import Form
from obi_one.core.block import Block
from obi_one.core.single import SingleCoordinateMixin
from obi_one.core.path import NamedPath

from obi_one.core.db import *

class SingleBlockGenerateTestForm(Form):
    """
    """
    _single_coord_class_name: str = "SingleBlockGenerateTest"

    class Initialize(Block):
        morphology_path: NamedPath | list[NamedPath]

    initialize: Initialize


import traceback
class SingleBlockGenerateTest(SingleBlockGenerateTestForm, SingleCoordinateMixin):
    
    def run(self):

        try:            
            with open(self.initialize.morphology_path, 'w') as file:
                file.write("Hello world!")

        except Exception as e:
            traceback.print_exception(e)
        
        return
        
        
from obi_one.core.db import *
class SingleBlockEntitySDKTestForm(Form):
    """
    """
    _single_coord_class_name: str = "SingleBlockGenerateTest"

    class Initialize(Block):
        morphology: ReconstructionMorphology | list[ReconstructionMorphology]

    initialize: Initialize

class SingleBlockEntitySDKTest(Form):

    def run(self):

        return


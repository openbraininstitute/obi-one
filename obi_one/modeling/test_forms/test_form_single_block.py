from pydantic import Field

from obi_one.core.form import Form
from obi_one.core.block import Block
from obi_one.core.single import SingleCoordinateMixin
from obi_one.core.path import NamedPath

from obi_one.database.entitysdk_classes import *

import traceback

"""
Test Form for testing the generation of a scan
"""
class SingleBlockGenerateTestForm(Form):
    """
    Test
    """
    _single_coord_class_name: str = "SingleBlockGenerateTest"

    class Initialize(Block):
        morphology_path: NamedPath | list[NamedPath]

    initialize: Initialize



class SingleBlockGenerateTest(SingleBlockGenerateTestForm, SingleCoordinateMixin):
    """
    Test
    """
    
    def run(self):

        try:            
            with open(self.initialize.morphology_path, 'w') as file:
                file.write("Hello world!")

        except Exception as e:
            traceback.print_exception(e)
        
        return
        
        


"""
Test Form for testing a single block form with entity SDK
"""
class SingleBlockEntitySDKTestForm(Form):
    """
    Test
    """
    _single_coord_class_name: str = "SingleBlockGenerateTest"

    class Initialize(Block):
        morphology: ReconstructionMorphology | list[ReconstructionMorphology]

    initialize: Initialize

class SingleBlockEntitySDKTest(SingleBlockEntitySDKTestForm, SingleCoordinateMixin):
    """
    Test
    """

    def run(self):

        return





"""
Test Form for testing a single block form with entity SDK
"""
class BlockForMultiBlockEntitySDKTest(Block):
    morphology_2: ReconstructionMorphology | list[ReconstructionMorphology]


class MultiBlockEntitySDKTestForm(Form):
    """
    Test
    """
    _single_coord_class_name: str = "MultiBlockGenerateTest"

    test_blocks: dict[str, BlockForMultiBlockEntitySDKTest] = Field(description="Test blocks")

    class Initialize(Block):
        morphology: ReconstructionMorphology | list[ReconstructionMorphology]

    initialize: Initialize




class MultiBlockEntitySDKTest(MultiBlockEntitySDKTestForm, SingleCoordinateMixin):
    """
    Test
    """

    def run(self):

        return



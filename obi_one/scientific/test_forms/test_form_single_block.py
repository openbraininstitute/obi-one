from pydantic import Field

from obi_one.core.form import Form
from obi_one.core.block import Block
from obi_one.core.single import SingleCoordinateMixin
from obi_one.core.path import NamedPath

from obi_one.database.db_classes import ReconstructionMorphologyFromID

import traceback

from typing import ClassVar

"""
Test Form for testing the generation of a scan
"""
class SingleBlockGenerateTestForm(Form):
    """
    Test
    """
    single_coord_class_name: ClassVar[str] = "SingleBlockGenerateTest"

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
class SingleBlockEntityTestForm(Form):
    """
    Test
    """
    single_coord_class_name: ClassVar[str] = "SingleBlockGenerateTest"

    class Initialize(Block):
        morphology: ReconstructionMorphologyFromID | list[ReconstructionMorphologyFromID]

    initialize: Initialize

class SingleBlockEntitySDKTest(SingleBlockEntityTestForm, SingleCoordinateMixin):
    """
    Test
    """

    def run(self):

        return





"""
Test Form for testing a single block form with entity SDK
"""
class BlockForMultiBlockEntitySDKTest(Block):
    morphology_2: ReconstructionMorphologyFromID | list[ReconstructionMorphologyFromID]


class MultiBlockEntitySDKTestForm(Form):
    """
    Test
    """
    single_coord_class_name: ClassVar[str] = "MultiBlockGenerateTest"

    test_blocks: dict[str, BlockForMultiBlockEntitySDKTest] = Field(description="Test blocks")

    class Initialize(Block):
        morphology: ReconstructionMorphologyFromID | list[ReconstructionMorphologyFromID]

    initialize: Initialize




class MultiBlockEntitySDKTest(MultiBlockEntitySDKTestForm, SingleCoordinateMixin):
    """
    Test
    """

    def run(self):

        return



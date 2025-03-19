from obi.modeling.core.form import Form
from obi.modeling.core.block import Block
from obi.modeling.core.single import SingleCoordinateMixin
from obi.modeling.core.base import NamedPath

class BasicConnectivityPlots(Form):
    """
    Class to generate basic connectivity plots and stats from a ConnectivityMatrix object.
    """

    _single_coord_class_name = "BasicConnectivityPlot"

    class Initialize(Block):
        matrix_path: NamedPath | list[NamedPath]
        # TODO: implement node population option
        # node_population: None | str | list[None | str] = None
        plot_formats:  None|tuple[str, ...] = None

    initialize: Initialize


import os
from conntility.connectivity import ConnectivityMatrix
from typing import ClassVar

class BasicConnectivityPlot(BasicConnectivityPlots, SingleCoordinateMixin):
    """
    #TODO: Add docstring
    """
    DEFAULT_FORMATS: ClassVar [tuple[str, ...]] = ("png", "pdf",  "svg")

    def run(self) -> None:

        try:
            print(f"Info: Running idx {self.idx}")

            #TODO: Fis handling of files. 
            # output_file = os.path.join(self.coordinate_output_root, "connectivity_matrix.h5")
            #assert not os.path.exists(output_file), f"Output file '{output_file}' already exists!"

            # Load matrix
            print(f"Info: Loading matrix '{self.initialize.matrix_path}'")
            adj = ConnectivityMatrix.from_h5(self.initialize.matrix_path.path).matrix
            # Set plot format output
            if self.initialize.plot_formats is None:
                plot_formats = self.DEFAULT_FORMATS
            else:
                plot_formats = self.initialize.plot_formats

            # TODO: DO SOMETHING HERE

            print(f"The connectivity matrix has shape {adj.shape}")
            print(f"The file formats required are {plot_formats}")


                                                   

            # Save to file
            # cmat.to_h5(output_file)
            # if os.path.exists(output_file):
            #     print(f"Info: Connectivity matrix successfully written to '{output_file}'")

        except Exception as e:
            print(f"Error: {e}")

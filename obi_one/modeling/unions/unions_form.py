from obi_one.modeling.unions.unions import subclass_union
from obi_one.core.form import Form
from obi_one.modeling.simulation.simulations import *
from obi_one.modeling.circuit_extraction.circuit_extraction import *
from obi_one.modeling.connectivity_matrix_extraction.connectivity_matrix_extraction import *
from obi_one.modeling.basic_connectivity_plots.basic_connectivity_plots import *
from obi_one.modeling.folder_compression.folder_compression import *
from obi_one.modeling.morphology_containerization.morphology_containerization import *
from obi_one.modeling.morphology_metrics.morphology_metrics import *
from obi_one.modeling.morphology_metrics.morphology_metrics_example import *
from obi_one.modeling.test_forms.test_form_single_block import *


FormUnion = subclass_union(Form)


from typing import get_type_hints
def check_implmentations_of_single_coordinate_class_and_methods_and_return_types(model: Type[Form], processing_method: str, data_postprocessing_method: str):
    """
    Method to return the class of the return type of a processing_method of the single coordinate class.
    Returns None if return type not specified
    Returns message strings if the processing_method or data_postprocessing_method are not implementd
    """

    return_class = None

    # Check that the single_coord_class_name is set
    if model.single_coord_class_name == "":
        return f"single_coord_class_name is not set in the form: {model.__name__}"
    else:
        single_coordinate_cls = globals().get(model.single_coord_class_name)
        if single_coordinate_cls is None:
            return f"Class {model.single_coord_class_name} not found in globals"

        # Check that the method is a method of the single coordinate class

        
        if not (hasattr(single_coordinate_cls, processing_method) and callable(getattr(single_coordinate_cls, processing_method))):
            return f"{processing_method} is not a method of {single_coordinate_cls.__name__}"
        else:

            if data_postprocessing_method == "":
                return None

            # Check that the data_postprocessing_method is a method of the single coordinate class
            if not (hasattr(single_coordinate_cls, data_postprocessing_method) and callable(getattr(single_coordinate_cls, data_postprocessing_method))):
                return f"{data_postprocessing_method} is not a method of {single_coordinate_cls.__name__}"
            else:
                return_class = get_type_hints(getattr(single_coordinate_cls, data_postprocessing_method)).get('return')

    return return_class
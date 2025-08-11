import copy
import json
import logging
from collections import OrderedDict
from importlib.metadata import version
from itertools import product
from pathlib import Path

import entitysdk
from pydantic import PrivateAttr, ValidationError

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.param import MultiValueScanParam, SingleValueScanParam
from obi_one.core.single import SingleCoordinateMixin, SingleCoordinateScanParams
from obi_one.scientific.unions.unions_form import FormUnion

L = logging.getLogger(__name__)


class MultiplyConfigs(OBIBaseModel):
    """Takes a Form & output_root as input.

    - Creates multi-dimensional parameter scans through calls to generate and run
    - Includes several intermediate functions for computing multi-dimensional parameter scans:
        i.e. multiple_value_parameters, coordinate_parameters, coordinate_instances
    """

    form: FormUnion
    output_root: Path = Path()
    coordinate_directory_option: str = "NAME_EQUALS_VALUE"
    _multiple_value_parameters: list = None
    _coordinate_parameters: list = PrivateAttr(default=[])
    _coordinate_instances: list = PrivateAttr(default=[])

    @property
    def output_root_absolute(self) -> Path:
        """Returns the absolute path of the output_root."""
        L.info(self.output_root.resolve())
        return self.output_root.resolve()

    def multiple_value_parameters(self, *, display: bool = False) -> list[MultiValueScanParam]:
        """Iterates through Blocks of self.form to find "multi value parameters".

            (i.e. parameters with list values of length greater than 1)
        - Returns a list of MultiValueScanParam objects
        """
        self._multiple_value_parameters = []

        # Iterate through all attributes of the Form
        for attr_name, attr_value in self.form.__dict__.items():
            # Check if the attribute is a dictionary of Block instances
            if isinstance(attr_value, dict) and all(
                isinstance(dict_val, Block) for dict_key, dict_val in attr_value.items()
            ):
                category_name = attr_name
                category_blocks_dict = attr_value

                # If so iterate through the dictionary's Block instances
                for block_key, block in category_blocks_dict.items():
                    # Call the multiple_value_parameters method of the Block instance
                    block_multi_value_parameters = block.multiple_value_parameters(
                        category_name=category_name, block_key=block_key
                    )
                    if len(block_multi_value_parameters):
                        self._multiple_value_parameters.extend(block_multi_value_parameters)

            # Else if the attribute is a Block instance, call the _multiple_value_parameters method
            # of the Block instance
            if isinstance(attr_value, Block):
                block_name = attr_name
                block = attr_value
                block_multi_value_parameters = block.multiple_value_parameters(
                    category_name=block_name
                )
                if len(block_multi_value_parameters):
                    self._multiple_value_parameters.extend(block_multi_value_parameters)

        # Optionally display the multiple_value_parameters
        if display:
            L.info("\nMULTIPLE VALUE PARAMETERS")
            if len(self._multiple_value_parameters) == 0:
                L.info("No multiple value parameters found.")
            else:
                for multi_value in self._multiple_value_parameters:
                    L.info(f"{multi_value.location_str}: {multi_value.values}")

        # Return the multiple_value_parameters
        return self._multiple_value_parameters

    @property
    def multiple_value_parameters_dictionary(self) -> dict:
        d = {}
        for multi_value in self.multiple_value_parameters():
            d[multi_value.location_str] = multi_value.values

        return d

    def coordinate_parameters(self, *, display: bool = False) -> list[SingleCoordinateScanParams]:
        """Must be implemented by a subclass of Scan."""
        msg = "coordinate_parameters() must be implemented by a subclass of Scan."
        raise NotImplementedError(msg)

    def coordinate_instances(self, *, display: bool = False) -> list[SingleCoordinateMixin]:
        """Coordinate instance.

        - Returns a list of "coordinate instances" by:
            - Iterating through self.coordinate_parameters()
            - Creating a single "coordinate instance" for each single coordinate parameter

        - Each "coordinate instance" is created by:
            - Making a deep copy of the form
            - Editing the multi value parameters (lists) to have the values of the single
                coordinate parameters
                (i.e. timestamps.timestamps_1.interval = [1.0, 5.0] ->
                    timestamps.timestamps_1.interval = 1.0)
            - Casting the form to its single_coord_class_name type
                (i.e. SimulationsForm -> Simulation)
        """
        self._coordinate_instances = []

        # Iterate through coordinate_parameters
        for idx, single_coordinate_scan_params in enumerate(self.coordinate_parameters()):
            # Make a deep copy of self.form
            single_coordinate_form = copy.deepcopy(self.form)

            # Iterate through parameters in the single_coordinate_parameters tuple
            # Change the value of the multi parameter from a list to the single value of the
            # coordinate
            for scan_param in single_coordinate_scan_params.scan_params:
                level_0_val = single_coordinate_form.__dict__[scan_param.location_list[0]]

                # If the first level is a Block
                if isinstance(level_0_val, Block):
                    level_0_val.__dict__[scan_param.location_list[1]] = scan_param.value

                # If the first level is a category dictionary
                if isinstance(level_0_val, dict):
                    level_1_val = level_0_val[scan_param.location_list[1]]
                    if isinstance(level_1_val, Block):
                        level_1_val.__dict__[scan_param.location_list[2]] = scan_param.value
                    else:
                        msg = f"Non Block parameter {level_1_val} found in Form dictionary: \
                            {level_0_val}"
                        raise TypeError(msg)

            try:
                # Cast the form to its single_coord_class_name type
                coordinate_instance = single_coordinate_form.cast_to_single_coord()

                # Set the variables of the coordinate instance related to the scan
                coordinate_instance.idx = idx
                coordinate_instance.single_coordinate_scan_params = single_coordinate_scan_params

                # Append the coordinate instance to self._coordinate_instances
                self._coordinate_instances.append(coordinate_instance)

            except ValidationError as e:
                raise ValidationError(e) from e

        # Optionally display the coordinate instances
        if display:
            L.info("\nCOORDINATE INSTANCES")
            for coordinate_instance in self._coordinate_instances:
                L.info(coordinate_instance)

        # Return self._coordinate_instances
        return self._coordinate_instances
    

    def execute(
        self,
        processing_method: str = "",
        data_postprocessing_method: str = "",
        db_client: entitysdk.client.Client = None,
        ) -> entitysdk.models.core.Identifiable:
        """Description."""
        # return_dict = {}

        L.info(db_client)

        if not processing_method:
            msg = "Processing method must be specified."
            raise ValueError(msg)

        Path.mkdir(self.output_root, parents=True, exist_ok=True)

        # Serialize the scan
        self.serialize(self.output_root / "run_scan_config.json")

        # Create a bbp_workflow_campaign_config
        self.create_bbp_workflow_campaign_config(
            self.output_root / "bbp_workflow_campaign_config.json"
        )

        single_entities = []

        # Iterate through self.coordinate_instances()
        for coordinate_instance in self.coordinate_instances():
            # Check if coordinate instance has function "run"
            if hasattr(coordinate_instance, processing_method):
                # Initialize the coordinate_instance's coordinate_output_root
                coordinate_instance.initialize_coordinate_output_root(
                    self.output_root, self.coordinate_directory_option
                )

                # Serialize the coordinate instance
                coordinate_instance.serialize(
                    coordinate_instance.coordinate_output_root / "run_coordinate_instance.json"
                )

        # return campaign
    

class GridMultiplyConfigs(MultiplyConfigs):
    """Description."""

    def coordinate_parameters(self, *, display: bool = False) -> list[SingleCoordinateScanParams]:
        """Description."""
        single_values_by_multi_value = []
        multi_value_parameters = self.multiple_value_parameters()
        if len(multi_value_parameters):
            for multi_value in multi_value_parameters:
                single_values = [
                    SingleValueScanParam(location_list=multi_value.location_list, value=value)
                    for value in multi_value.values
                ]

                single_values_by_multi_value.append(single_values)

            self._coordinate_parameters = []
            for scan_params in product(*single_values_by_multi_value):
                self._coordinate_parameters.append(
                    SingleCoordinateScanParams(scan_params=scan_params)
                )

        else:
            self._coordinate_parameters = [
                SingleCoordinateScanParams(
                    nested_coordinate_subpath_str=self.form.single_coord_scan_default_subpath
                )
            ]

        # Optionally display the coordinate parameters
        if display:
            self.display_coordinate_parameters()

        # Return the coordinate parameters
            return self._coordinate_parameters


class CoupledMultiplyConfigs(MultiplyConfigs):
    """Description."""

    def coordinate_parameters(self, *, display: bool = False) -> list:
        """Description."""
        previous_len = -1

        multi_value_parameters = self.multiple_value_parameters()
        if len(multi_value_parameters):
            for multi_value in multi_value_parameters:
                current_len = len(multi_value.values)
                if previous_len not in {-1, current_len}:
                    msg = f"Multi value parameters have different lengths: {previous_len} and \
                            {current_len}"
                    raise ValueError(msg)

                previous_len = current_len

            n_coords = current_len

            self._coordinate_parameters = []
            for coord_i in range(n_coords):
                scan_params = [
                    SingleValueScanParam(
                        location_list=multi_value.location_list,
                        value=multi_value.values[coord_i],
                    )
                    for multi_value in multi_value_parameters
                ]
                self._coordinate_parameters.append(
                    SingleCoordinateScanParams(scan_params=scan_params)
                )

        else:
            self._coordinate_parameters = [
                SingleCoordinateScanParams(
                    nested_coordinate_subpath_str=self.form.single_coord_scan_default_subpath
                )
            ]

        if display:
            self.display_coordinate_parameters()

        return self._coordinate_parameters

import logging
from itertools import product

from obi_one.core.param import SingleValueScanParam
from obi_one.core.scan_generation_task.base import ScanGenerationTask
from obi_one.core.single import SingleCoordinateScanParams

L = logging.getLogger(__name__)


class GridScanGenerationTask(ScanGenerationTask):
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

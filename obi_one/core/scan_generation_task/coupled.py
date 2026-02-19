import logging

from obi_one.core.param import SingleValueScanParam
from obi_one.core.scan_generation_task.base import ScanGenerationTask
from obi_one.core.single import SingleCoordinateScanParams

L = logging.getLogger(__name__)


class CoupledScanGenerationTask(ScanGenerationTask):
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

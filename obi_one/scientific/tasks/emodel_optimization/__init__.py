"""Tasks wrapping BluePyEModel's L5PC-style emodel optimisation pipeline.

The pipeline mirrors the four steps documented at
https://github.com/openbraininstitute/BluePyEModel/blob/main/examples/L5PC/README.rst:

* ``_01_efeature_extraction``: extract experimental e-features from raw traces.
* ``_02_emodel_optimization``: optimise model parameters against those features.
* ``_03_analysis_and_validation``: store results, validate, and plot.
* ``_04_export_final_model``: export the optimised model to HOC and SONATA.

Each stage is a standalone OBI-ONE :class:`~obi_one.core.scan_config.ScanConfig`
that materialises a self-contained BluePyEModel working directory inside the
single config's ``coordinate_output_root`` and runs the BluePyEModel API after
``chdir`` into that directory. Stages 01-03 read the previous stage's working
directory through a ``previous_stage_output_path`` field.
"""

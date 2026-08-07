"""Tasks wrapping BluePyEModel's L5PC-style emodel optimisation pipeline.

The pipeline mirrors the steps documented at
https://github.com/openbraininstitute/BluePyEModel/blob/main/examples/L5PC/README.rst:

* ``efeature_extraction``: extract experimental e-features from raw traces.
* ``emodel_optimization``: optimise model parameters, run analysis, and export
  draft emodel (Workflow A — merged optimisation + analysis + export).
* ``export_and_validation``: validate optimised models, plot validation
  figures, and re-export only validated models to HOC/SONATA (Workflow B).

Each stage is a standalone OBI-ONE :class:`~obi_one.core.scan_config.ScanConfig`
that materialises a self-contained BluePyEModel working directory inside the
single config's ``coordinate_output_root`` and runs the BluePyEModel API after
``chdir`` into that directory. Stages consume the previous stage's
``TaskResult`` entity and download its assets to seed the working directory.
"""

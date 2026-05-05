"""Task wrapper for the BluePyEModel export step."""

import logging
from pathlib import Path
from typing import ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.tasks.emodel_optimization import _shared
from obi_one.scientific.tasks.emodel_optimization._04_export_final_model.config import (
    EModelExportFinalModelSingleConfig,
)

L = logging.getLogger(__name__)


class EModelExportFinalModelTask(Task):
    """Run ``export_emodels_hoc`` and ``export_emodels_sonata`` for one config."""

    name: ClassVar[str] = "EModel Export Final Model"
    description: ClassVar[str] = "Export the optimised BluePyEModel models to HOC and/or SONATA."

    config: EModelExportFinalModelSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,  # noqa: ARG002
    ) -> Path:
        from bluepyemodel.emodel_pipeline.emodel_pipeline import (  # noqa: PLC0415
            EModel_pipeline,
        )
        from bluepyemodel.export_emodel.export_emodel import (  # noqa: PLC0415
            export_emodels_hoc,
            export_emodels_sonata,
        )

        init = self.config.initialize
        settings = self.config.export_settings
        coord_root = Path(self.config.coordinate_output_root).resolve()
        previous = Path(init.previous_stage_output_path).resolve()

        _shared.seed_working_dir_from_previous(previous, coord_root)

        if (
            not (coord_root / "x86_64" / "special").exists()
            and not (coord_root / "arm64" / "special").exists()
        ):
            _shared.compile_mechanisms(coord_root / "mechanisms")

        with _shared.chdir(coord_root):
            pipeline = EModel_pipeline(
                emodel=init.emodel,
                etype=init.etype,
                mtype=init.mtype,
                ttype=init.ttype,
                species=init.species,
                brain_region=init.brain_region,
                recipes_path="./config/recipes.json",
                iteration_tag=init.iteration_tag,
                use_ipyparallel=init.use_ipyparallel,
                use_multiprocessing=init.use_multiprocessing,
            )

            if settings.export_hoc:
                export_emodels_hoc(
                    pipeline.access_point,
                    only_validated=settings.only_validated,
                    only_best=settings.only_best,
                    seeds=list(settings.seeds),
                )

            if settings.export_sonata:
                export_emodels_sonata(
                    pipeline.access_point,
                    only_validated=settings.only_validated,
                    only_best=settings.only_best,
                    seeds=list(settings.seeds),
                    map_function=pipeline.mapper,
                )

        return coord_root

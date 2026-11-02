from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd

from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.tasks.morphology_locations import MorphologyLocationsTask


def test_entity_morphology_is_called_with_database_client(tmp_path):
    morphology = MagicMock()
    db_client = MagicMock()
    morph_locations = MagicMock()
    morph_locations.points_on.return_value = pd.DataFrame()
    plot = MagicMock()
    reference = CellMorphologyFromID(id_str="morphology-id")
    config = SimpleNamespace(
        initialize=SimpleNamespace(morphology=reference),
        morph_locations=morph_locations,
        coordinate_output_root=tmp_path,
    )
    task = MorphologyLocationsTask.model_construct(config=config)

    with (
        patch.object(CellMorphologyFromID, "morphio_morphology", return_value=morphology) as load,
        patch.object(MorphologyLocationsTask, "generate_plot", return_value=plot) as generate_plot,
    ):
        task.execute(db_client=db_client)

    load.assert_called_once_with(db_client=db_client)
    morph_locations.points_on.assert_called_once_with(morphology)
    generate_plot.assert_called_once_with(morphology, morph_locations.points_on.return_value)
    plot.savefig.assert_called_once_with(tmp_path / "locations_plot.pdf")

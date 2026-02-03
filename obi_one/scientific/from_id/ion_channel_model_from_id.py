from pathlib import Path
from typing import ClassVar

import entitysdk
from entitysdk.models import IonChannelModel
from entitysdk.models.entity import Entity
from entitysdk.types import ContentType
from entitysdk.utils.filesystem import create_dir
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import EntityFromID


class IonChannelModelFromID(EntityFromID):
    entitysdk_class: ClassVar[type[Entity]] = IonChannelModel
    _entity: IonChannelModel | None = PrivateAttr(default=None)

    def download_asset(
        self, dest_dir: Path = Path(), db_client: entitysdk.client.Client = None
    ) -> Path:
        output_dir = create_dir(dest_dir)
        asset = db_client.download_assets(
            self.entity(db_client=db_client),
            selection={"content_type": ContentType.application_mod},
            output_path=output_dir,
        ).one()

        return asset.path
    
    def get_conductance_name(self, db_client: entitysdk.client.Client = None) -> str|None:
        """Returns the conductance name if present, else return None."""
        return self.entity(db_client=db_client).conductance_name

    def has_conductance(self, db_client: entitysdk.client.Client = None) -> bool:
        """Returns True if the ion channel model has a conductance name."""
        return self.get_conductance_name(db_client=db_client) is not None
    
    def get_max_permeability_name(self, db_client: entitysdk.client.Client = None) -> str|None:
        """Returns the max permeability name if present, else return None."""
        return self.entity(db_client=db_client).max_permeability_name

    def has_max_permeability(self, db_client: entitysdk.client.Client = None) -> bool:
        """Returns True if the ion channel model has a max permeability name."""
        return self.get_max_permeability_name(db_client=db_client) is not None

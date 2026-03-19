from entitysdk import Client
from entitysdk.models import Entity
from entitysdk.models.asset import Asset
from entitysdk.types import AssetLabel

def get_config_asset(*, client: Client, config: Entity, asset_label: AssetLabel) -> Asset:
    """Determines the asset ID of the JSON config asset."""
    return client.select_assets(entity=config, selection={"label": asset_label}).one()
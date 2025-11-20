from typing import ClassVar

import numpy  # NOQA: ICN001
import pandas  # NOQA: ICN001
from caveclient import CAVEclient
from entitysdk import Client
from entitysdk.models import EMDenseReconstructionDataset
from entitysdk.models.entity import Entity
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import EntityFromID

_C_P_LOCS = ["synapse_x", "synapse_y", "synapse_z"]
_NM_to_UM = 1e-3


class EMDataSetFromID(EntityFromID):
    entitysdk_class: ClassVar[type[Entity]] = EMDenseReconstructionDataset
    _entity: EMDenseReconstructionDataset | None = PrivateAttr(default=None)
    _viewer_resolution: numpy.ndarray | None = PrivateAttr(default=None)
    auth_token: str | None = None

    def synapse_info_df(
        self,
        pt_root_id: int,
        cave_version: int,
        db_client: Client | None = None,
        col_location: str = "ctr_pt_position",
    ) -> tuple[pandas.DataFrame, str]:
        client = self._make_cave_client(db_client, cave_version=cave_version)
        if self._viewer_resolution is None:
            self._viewer_resolution = client.info.viewer_resolution()

        if not isinstance(pt_root_id, list):
            pt_root_id = [pt_root_id]
        syns = client.materialize.synapse_query(post_ids=pt_root_id)

        syn_locs = syns[col_location].apply(
            lambda _x: pandas.Series(
                _NM_to_UM * _x * self.viewer_resolution(db_client=db_client), index=_C_P_LOCS
            )
        )
        syns = pandas.concat([syns, syn_locs], axis=1).reset_index(drop=True)
        syns.index.name = "synapse_id"

        notice_text = client.materialize.get_table_metadata(client.materialize.synapse_table).get(
            "notice_text"
        )
        return syns, notice_text

    def neuron_info_df(
        self, table_name: str, cave_version: int, db_client: Client | None = None
    ) -> tuple[pandas.DataFrame, str]:
        client = self._make_cave_client(db_client, cave_version=cave_version)
        tbl = client.materialize.query_table(table_name)
        counts = tbl["pt_root_id"].value_counts()
        tbl = tbl.set_index("pt_root_id").loc[counts.index[counts == 1]]

        notice_text = client.materialize.get_table_metadata(table_name).get("notice_text")
        return tbl, notice_text

    def get_versions(self, db_client: Client | None = None) -> list:
        client = self._make_cave_client(db_client)
        return client.materialize.get_versions()

    def get_tables(self, cave_version: int, db_client: Client | None = None) -> dict:
        client = self._make_cave_client(db_client, cave_version=cave_version)
        tables = {}
        for tbl_name in client.materialize.get_tables():
            meta = client.materialize.get_table_metadata(tbl_name)
            tables[tbl_name] = {
                "description": meta["description"],
                "notice": meta["notice_text"],
            }
        return tables

    def viewer_resolution(self, db_client: Client | None = None) -> list:
        if self._viewer_resolution is None:
            self._viewer_resolution = self._make_cave_client(
                db_client=db_client
            ).info.viewer_resolution()
        return self._viewer_resolution

    def _make_cave_client(self, db_client: Client, cave_version: int | None = None) -> CAVEclient:
        entity = self.entity(db_client=db_client)
        datastack_name_ = entity.cave_datastack
        cave_client_url_ = entity.cave_client_url

        cave_client = CAVEclient(
            datastack_name_, server_address=cave_client_url_, auth_token=self.auth_token
        )
        cave_client.version = cave_version
        return cave_client

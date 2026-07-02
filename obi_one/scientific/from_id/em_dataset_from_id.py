import functools
from collections.abc import Callable
from typing import ClassVar

import numpy  # NOQA: ICN001
import pandas  # NOQA: ICN001
import requests
from caveclient import CAVEclient, set_session_defaults
from entitysdk import Client
from entitysdk.models import EMDenseReconstructionDataset
from entitysdk.models.entity import Entity
from pydantic import PrivateAttr

from obi_one.config import settings
from obi_one.core.entity_from_id import EntityFromID
from obi_one.core.exception import OBIONEError

_C_P_LOCS = ["synapse_x", "synapse_y", "synapse_z"]
_NM_to_UM = 1e-3


def _graceful_materialize_errors[T](func: Callable[..., T]) -> Callable[..., T]:
    """Convert exhausted CAVEClient request failures into a clean OBIONEError.

    The CAVEClient materialization engine intermittently returns transient errors
    (e.g. 503). caveclient retries these at the HTTP-session layer (see
    ``_make_cave_client``); once retries are exhausted it raises a ``requests``
    exception. This decorator translates that into an actionable ``OBIONEError``
    so the task fails gracefully rather than with a raw traceback.

    Args:
        func: The materialize-backed method to wrap.

    Returns:
        The wrapped method.
    """

    @functools.wraps(func)
    def wrapper(*args: object, **kwargs: object) -> T:
        try:
            return func(*args, **kwargs)
        except requests.exceptions.RequestException as e:
            msg = (
                "The EM materialization engine is temporarily unavailable after "
                f"retries; please try again later (underlying error: {e})."
            )
            raise OBIONEError(msg) from e

    return wrapper


def _configure_caveclient_retries() -> None:
    """Widen caveclient's process-global retry behaviour from settings.

    The CAVEClient materialization engine intermittently returns transient errors
    (e.g. 503). caveclient retries 502/503/504 at the HTTP-session layer but with
    weak defaults; this widens them so transient outages are ridden out before
    failing. ``set_session_defaults`` mutates a process-global dict that applies to
    every client created afterwards, so it is invoked once at import time below.
    """
    cfg = settings.cave_client_config
    set_session_defaults(
        max_retries=cfg.max_retries,
        backoff_factor=cfg.retry_backoff_factor,
        backoff_max=cfg.retry_backoff_max,
        status_forcelist=cfg.retry_status_forcelist,
    )


_configure_caveclient_retries()


class EMDataSetFromID(EntityFromID):
    entitysdk_class: ClassVar[type[Entity]] = EMDenseReconstructionDataset
    _entity: EMDenseReconstructionDataset | None = PrivateAttr(default=None)
    _viewer_resolution: numpy.ndarray | None = PrivateAttr(default=None)
    auth_token: str | None = None

    @_graceful_materialize_errors
    def synapse_info_df(
        self,
        pt_root_id: int,
        cave_version: int,
        db_client: Client | None = None,
        col_location: str = "ctr_pt_position",
    ) -> tuple[pandas.DataFrame, str]:
        client = self._make_cave_client(db_client, cave_version=cave_version)  # ty:ignore[invalid-argument-type]
        if self._viewer_resolution is None:
            self._viewer_resolution = client.info.viewer_resolution()  # ty:ignore[unresolved-attribute]

        if not isinstance(pt_root_id, list):
            pt_root_id = [pt_root_id]  # ty:ignore[invalid-assignment]
        syns = client.materialize.synapse_query(post_ids=pt_root_id)  # ty:ignore[unresolved-attribute]

        syn_locs = syns[col_location].apply(
            lambda _x: pandas.Series(
                _NM_to_UM * _x * self.viewer_resolution(db_client=db_client), index=_C_P_LOCS
            )
        )
        syns = pandas.concat([syns, syn_locs], axis=1).reset_index(drop=True)
        syns.index.name = "synapse_id"

        notice_text = client.materialize.get_table_metadata(client.materialize.synapse_table).get(  # ty:ignore[unresolved-attribute]
            "notice_text"
        )
        return syns, notice_text

    @_graceful_materialize_errors
    def neuron_info_df(
        self, table_name: str, cave_version: int, db_client: Client | None = None
    ) -> tuple[pandas.DataFrame, str]:
        client = self._make_cave_client(db_client, cave_version=cave_version)  # ty:ignore[invalid-argument-type]
        tbl = client.materialize.query_table(table_name)  # ty:ignore[unresolved-attribute]
        counts = tbl["pt_root_id"].value_counts()
        tbl = tbl.set_index("pt_root_id").loc[counts.index[counts == 1]]

        notice_text = client.materialize.get_table_metadata(table_name).get("notice_text")  # ty:ignore[unresolved-attribute]
        return tbl, notice_text

    @_graceful_materialize_errors
    def get_versions(self, db_client: Client | None = None) -> list:
        client = self._make_cave_client(db_client)  # ty:ignore[invalid-argument-type]
        return client.materialize.get_versions()  # ty:ignore[unresolved-attribute]

    @_graceful_materialize_errors
    def get_tables(self, cave_version: int, db_client: Client | None = None) -> dict:
        client = self._make_cave_client(db_client, cave_version=cave_version)  # ty:ignore[invalid-argument-type]
        tables = {}
        for tbl_name in client.materialize.get_tables():  # ty:ignore[unresolved-attribute]
            meta = client.materialize.get_table_metadata(tbl_name)  # ty:ignore[unresolved-attribute]
            tables[tbl_name] = {
                "description": meta["description"],
                "notice": meta["notice_text"],
            }
        return tables

    @_graceful_materialize_errors
    def viewer_resolution(self, db_client: Client | None = None) -> list:
        if self._viewer_resolution is None:
            self._viewer_resolution = self._make_cave_client(
                db_client=db_client  # ty:ignore[invalid-argument-type]
            ).info.viewer_resolution()  # ty:ignore[unresolved-attribute]
        return self._viewer_resolution  # ty:ignore[invalid-return-type]

    def _make_cave_client(self, db_client: Client, cave_version: int | None = None) -> CAVEclient:
        entity = self.entity(db_client=db_client)
        datastack_name_ = entity.cave_datastack  # ty:ignore[unresolved-attribute]
        cave_client_url_ = entity.cave_client_url  # ty:ignore[unresolved-attribute]

        cave_client = CAVEclient(
            datastack_name_, server_address=cave_client_url_, auth_token=self.auth_token
        )
        cave_client.version = cave_version  # ty:ignore[unresolved-attribute]
        return cave_client

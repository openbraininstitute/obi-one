"""Derive electrical cell recording properties from entitysdk recordings.

Combines the protocol names stored on each ``ElectricalCellRecording`` with the
per-protocol step amplitudes (nA) read from its NWB asset, fetching every recording
exactly once.
"""

import tempfile
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

from entitysdk import Client
from entitysdk.models import ElectricalCellRecording
from entitysdk.types import AssetLabel, ContentType

from obi_one.scientific.library.electrical_cell_recording_properties import (
    read_amplitudes_from_nwb,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.protocols import (  # ruff: ignore[line-too-long]
    protocol_class_name_for,
)


def get_electrical_cell_recording_properties(
    recording_ids: list[UUID],
    db_client: Client,
) -> tuple[dict[str, list[str]], dict[str, list[float]]]:
    """Return protocols per recording and amplitudes per protocol in a single pass.

    Each ``ElectricalCellRecording`` is fetched once. Its stimulus names give the
    protocol names, and its NWB asset gives the step amplitudes (nA). Returns
    ``({recording_id: [protocol_class_name, ...]},
    {protocol_class_name: [step_amplitude_nA, ...]})``.
    """
    by_recording: dict[str, list[str]] = {}
    combined: defaultdict[str, set[float]] = defaultdict(set)
    for entity in _iter_recording_entities(recording_ids, db_client):
        by_recording[str(entity.id)] = _protocol_class_names(entity)
        for protocol, amplitudes in _amplitudes_by_protocol(entity, db_client).items():
            combined[protocol] |= amplitudes
    return by_recording, {protocol: sorted(amplitudes) for protocol, amplitudes in combined.items()}


def _iter_recording_entities(
    recording_ids: list[UUID],
    db_client: Client,
) -> Iterator[ElectricalCellRecording]:
    """Yield each recording once, preserving the input order."""
    seen: set[UUID] = set()
    for recording_id in recording_ids:
        if recording_id in seen:
            continue
        seen.add(recording_id)
        yield db_client.get_entity(
            entity_id=recording_id,
            entity_type=ElectricalCellRecording,
        )


def _protocol_class_names(entity: ElectricalCellRecording) -> list[str]:
    """Return the sorted ``Protocol`` subclass names matching the entity's stimuli."""
    return sorted(
        {
            class_name
            for stimulus in (entity.stimuli or [])
            if stimulus.name and (class_name := protocol_class_name_for(stimulus.name)) is not None
        }
    )


def _amplitudes_by_protocol(
    entity: ElectricalCellRecording,
    db_client: Client,
) -> dict[str, set[float]]:
    """Return the entity's NWB step amplitudes (nA), keyed by protocol class name."""
    protocol_names = sorted({s.name for s in (entity.stimuli or []) if s.name})
    if not protocol_names:
        return {}

    with tempfile.TemporaryDirectory() as tmp:
        asset = db_client.fetch_assets(
            entity,
            selection={"content_type": ContentType.application_nwb, "label": AssetLabel.nwb},
            output_path=Path(tmp),
        ).one()
        per_protocol = read_amplitudes_from_nwb(Path(asset.path), protocol_names)

    by_protocol: defaultdict[str, set[float]] = defaultdict(set)
    for raw_name, amplitudes in per_protocol.items():
        class_name = protocol_class_name_for(raw_name)
        if class_name is not None:
            by_protocol[class_name] |= set(amplitudes)
    return by_protocol

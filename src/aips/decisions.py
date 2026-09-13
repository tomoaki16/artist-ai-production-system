"""Validate Artist decisions and build an explicit AI data boundary."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from .dawproject import DawprojectError


VALID_USAGE = {"use", "reference", "ignore"}
VALID_ROLES = {"drums", "bass", "guitar", "keys", "unknown"}


def load_decisions(path: str | Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DawprojectError(f"invalid Artist decisions JSON: {path}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("track_decisions"), list):
        raise DawprojectError("Artist decisions must contain a track_decisions array")
    return data


def prepare_ai_payload(context: dict[str, Any], decisions: dict[str, Any]) -> dict[str, Any]:
    """Apply explicit Artist decisions without silently filling missing tracks."""
    tracks = {str(track["id"]): track for track in context.get("tracks", [])}
    chosen: dict[str, dict[str, str]] = {}
    for item in decisions["track_decisions"]:
        if not isinstance(item, dict):
            raise DawprojectError("each track decision must be an object")
        track_id = str(item.get("track_id", ""))
        usage = item.get("usage")
        role = item.get("role")
        if track_id not in tracks:
            raise DawprojectError(f"unknown track in Artist decisions: {track_id}")
        if track_id in chosen:
            raise DawprojectError(f"duplicate track decision: {track_id}")
        if usage not in VALID_USAGE:
            raise DawprojectError(f"invalid usage for {track_id}: {usage}")
        if role not in VALID_ROLES:
            raise DawprojectError(f"invalid role for {track_id}: {role}")
        chosen[track_id] = {"usage": usage, "role": role}
    missing = sorted(set(tracks) - set(chosen))
    if missing:
        raise DawprojectError(f"Artist decision is missing for tracks: {', '.join(missing)}")

    included = []
    editable_ids = []
    reference_ids = []
    ignored = []
    for track_id, track in tracks.items():
        decision = chosen[track_id]
        if decision["usage"] == "ignore":
            ignored.append({"id": track_id, "name": track["name"]})
            continue
        exported = deepcopy(track)
        exported["role"] = decision["role"]
        exported["artist_usage"] = decision["usage"]
        exported["locked"] = decision["usage"] == "reference"
        included.append(exported)
        (reference_ids if exported["locked"] else editable_ids).append(track_id)

    return {
        "schema_version": "0.1",
        "purpose": "music_analysis_and_proposal",
        "project": {
            "application": context.get("application"),
            "transport": context.get("transport"),
            "selection": context.get("selection"),
            "harmony": context.get("harmony"),
            "tracks": included,
        },
        "artist_authority": {
            "editable_track_ids": editable_ids,
            "reference_only_track_ids": reference_ids,
            "rule": "Reference-only tracks may inform analysis but must not be modified.",
        },
        "excluded_from_ai": ignored,
    }

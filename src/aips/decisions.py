"""Validate Artist decisions and build an explicit AI data boundary."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from .dawproject import DawprojectError


VALID_USAGE = {"use", "reference", "ignore"}
VALID_ROLES = {"drums", "bass", "guitar", "keys", "unknown"}
VALID_AUTHORITY = {"protect", "open"}


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


def load_confirmed_analysis(path: str | Path) -> dict[str, Any]:
    """Load and validate the Artist-confirmed musical facts."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DawprojectError(f"invalid confirmed analysis JSON: {path}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("bar_decisions"), list):
        raise DawprojectError("confirmed analysis must contain bar_decisions")
    seen = set()
    for decision in data["bar_decisions"]:
        if not isinstance(decision, dict) or not isinstance(decision.get("bar"), int):
            raise DawprojectError("each confirmed decision needs an integer bar")
        if decision["bar"] in seen:
            raise DawprojectError(f"duplicate confirmed bar: {decision['bar']}")
        seen.add(decision["bar"])
        parts = decision.get("parts")
        if not isinstance(parts, dict) or set(parts) != {"harmony", "bass", "guitar"}:
            raise DawprojectError("each bar must confirm harmony, bass and guitar")
        for name, part in parts.items():
            if not isinstance(part, dict) or not str(part.get("value", "")).strip():
                raise DawprojectError(f"bar {decision['bar']} has an empty {name} value")
            if part.get("authority") not in VALID_AUTHORITY:
                raise DawprojectError(f"bar {decision['bar']} has invalid {name} authority")
    return data


def prepare_producer_request(confirmed: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    """Create a provider-neutral request whose protected facts are enforceable."""
    intent = str(brief.get("artist_intent", "")).strip()
    if not intent:
        raise DawprojectError("Artist intent is required")
    constraints = brief.get("constraints", [])
    if isinstance(constraints, str):
        constraints = [line.strip() for line in constraints.splitlines() if line.strip()]
    if not isinstance(constraints, list) or not all(isinstance(item, str) for item in constraints):
        raise DawprojectError("constraints must be a string array")
    proposal_count = int(brief.get("proposal_count", 3))
    if not 1 <= proposal_count <= 5:
        raise DawprojectError("proposal_count must be between 1 and 5")

    bars = []
    protected = []
    editable = []
    for bar_decision in confirmed["bar_decisions"]:
        bar = bar_decision["bar"]
        context = {}
        authority = {}
        for part_name, part in bar_decision["parts"].items():
            value = str(part["value"]).strip()
            context[part_name] = value
            authority[part_name] = part["authority"]
            target = {"bar": bar, "part": part_name, "value": value}
            (protected if part["authority"] == "protect" else editable).append(target)
        bars.append({"bar": bar, "confirmed_context": context, "authority": authority})

    return {
        "schema_version": "0.1",
        "purpose": "producer_arrangement_proposals",
        "artist": {
            "intent": intent,
            "constraints": constraints,
            "owns_taste_and_final_decision": True,
        },
        "music_context": {"bars": bars, "source": "artist_confirmed_analysis"},
        "authority_boundary": {
            "protected": protected,
            "editable": editable,
            "rule": "Never alter protected values. Propose changes only for editable parts.",
        },
        "requested_output": {
            "proposal_count": proposal_count,
            "return_multiple_options": True,
            "include_short_rationale": True,
            "format": "structured_music_proposals",
        },
    }

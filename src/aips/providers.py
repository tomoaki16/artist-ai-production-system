"""Provider-neutral AI boundary and response validation."""

from __future__ import annotations

from typing import Any, Protocol

from .dawproject import DawprojectError


class ProducerProvider(Protocol):
    """Minimal contract implemented by every user-selected AI connector."""

    def generate(self, envelope: dict[str, Any]) -> dict[str, Any]: ...


def create_provider_envelope(request: dict[str, Any]) -> dict[str, Any]:
    """Wrap one Producer Request without depending on a provider's API shape."""
    return {
        "schema_version": "0.1",
        "role": "AI Producer and Engineer",
        "non_negotiable_rules": [
            "The Artist owns taste and final decisions.",
            "Never modify a protected item.",
            "Only propose changes to targets listed as editable.",
            "Return structured data matching the response contract.",
        ],
        "request": request,
        "response_contract": {
            "schema_version": "0.1",
            "proposals": [{
                "id": "unique string",
                "title": "short name",
                "rationale": "short musical reason",
                "changes": [{
                    "bar": "integer", "part": "harmony | bass | guitar",
                    "from_value": "confirmed value", "to_value": "proposed value",
                    "reason": "musical reason",
                }],
                "midi_events": [{
                    "bar": "integer", "part": "bass | guitar | drums",
                    "beat": "0-based number within bar", "duration_beats": "positive number",
                    "pitch": "MIDI note 0-127", "velocity": "1-127",
                }],
            }],
        },
    }


def validate_producer_response(request: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    """Reject AI output that crosses an Artist-defined authority boundary."""
    if not isinstance(response, dict) or not isinstance(response.get("proposals"), list):
        raise DawprojectError("Producer response must contain a proposals array")
    proposals = response["proposals"]
    expected = int(request.get("requested_output", {}).get("proposal_count", 3))
    if not 1 <= len(proposals) <= expected:
        raise DawprojectError(f"Producer response must contain between 1 and {expected} proposals")

    editable = {
        (int(item["bar"]), str(item["part"])): str(item["value"])
        for item in request.get("authority_boundary", {}).get("editable", [])
    }
    proposal_ids = set()
    normalized = []
    for proposal in proposals:
        if not isinstance(proposal, dict):
            raise DawprojectError("each proposal must be an object")
        proposal_id = str(proposal.get("id", "")).strip()
        title = str(proposal.get("title", "")).strip()
        rationale = str(proposal.get("rationale", "")).strip()
        changes = proposal.get("changes")
        midi_events = proposal.get("midi_events", [])
        if (not proposal_id or not title or not rationale or not isinstance(changes, list)
                or not isinstance(midi_events, list)):
            raise DawprojectError("each proposal needs id, title, rationale, changes and optional midi_events")
        if proposal_id in proposal_ids:
            raise DawprojectError(f"duplicate proposal id: {proposal_id}")
        proposal_ids.add(proposal_id)
        seen_targets = set()
        normalized_changes = []
        for change in changes:
            try:
                bar = int(change["bar"])
                part = str(change["part"])
                from_value = str(change["from_value"]).strip()
                to_value = str(change["to_value"]).strip()
                reason = str(change["reason"]).strip()
            except (KeyError, TypeError, ValueError) as exc:
                raise DawprojectError("each proposed change is incomplete") from exc
            target = (bar, part)
            if target not in editable:
                raise DawprojectError(
                    f"proposal {proposal_id} attempts to change protected target: bar {bar} {part}"
                )
            if target in seen_targets:
                raise DawprojectError(
                    f"proposal {proposal_id} changes bar {bar} {part} more than once"
                )
            if from_value != editable[target]:
                raise DawprojectError(
                    f"proposal {proposal_id} does not preserve confirmed source value for bar {bar} {part}"
                )
            if not to_value or not reason:
                raise DawprojectError("proposed values and reasons cannot be empty")
            seen_targets.add(target)
            normalized_changes.append({
                "bar": bar, "part": part, "from_value": from_value,
                "to_value": to_value, "reason": reason,
            })
        normalized_midi = []
        for event in midi_events:
            try:
                bar, part = int(event["bar"]), str(event["part"])
                beat, duration = float(event["beat"]), float(event["duration_beats"])
                pitch, velocity = int(event["pitch"]), int(event["velocity"])
            except (KeyError, TypeError, ValueError) as exc:
                raise DawprojectError("each MIDI event is incomplete") from exc
            if (bar, part) not in editable:
                raise DawprojectError(
                    f"proposal {proposal_id} writes MIDI to protected target: bar {bar} {part}"
                )
            if not 0 <= beat < 4 or duration <= 0 or not 0 <= pitch <= 127 or not 1 <= velocity <= 127:
                raise DawprojectError(f"proposal {proposal_id} contains an invalid MIDI event")
            normalized_midi.append({"bar": bar, "part": part, "beat": beat,
                                    "duration_beats": duration, "pitch": pitch,
                                    "velocity": velocity})
        normalized.append({
            "id": proposal_id, "title": title,
            "rationale": rationale, "changes": normalized_changes,
            "midi_events": normalized_midi,
        })
    return {"schema_version": "0.1", "status": "validated", "proposals": normalized}

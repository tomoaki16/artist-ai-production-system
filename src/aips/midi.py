"""Standard MIDI File export for validated AI proposals."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .dawproject import DawprojectError


def export_proposal_midi(validated: dict[str, Any], output_dir: str | Path,
                         *, tempo_bpm: float = 90.0) -> list[Path]:
    """Write one editable Standard MIDI File per validated proposal."""
    try:
        import mido
    except ImportError as exc:
        raise DawprojectError("MIDI export requires mido") from exc
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for proposal in validated.get("proposals", []):
        events = proposal.get("midi_events", [])
        if not events:
            continue
        first_bar = min(int(event["bar"]) for event in events)
        midi = mido.MidiFile(type=1, ticks_per_beat=480, charset="utf-8")
        tempo_track = mido.MidiTrack()
        tempo_track.append(mido.MetaMessage("track_name", name=proposal["title"], time=0))
        tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo_bpm), time=0))
        tempo_track.append(mido.MetaMessage(
            "text", text=f"Place at bar {first_bar}; proposal {proposal['id']}", time=0
        ))
        midi.tracks.append(tempo_track)
        by_part: dict[str, list[dict[str, Any]]] = {}
        for event in events:
            by_part.setdefault(str(event["part"]), []).append(event)
        for part, part_events in sorted(by_part.items()):
            track = mido.MidiTrack()
            track.append(mido.MetaMessage("track_name", name=part, time=0))
            messages = []
            for event in part_events:
                start = ((int(event["bar"]) - first_bar) * 4 + float(event["beat"])) * 480
                end = start + float(event["duration_beats"]) * 480
                messages.append((round(start), 1, int(event["pitch"]), int(event["velocity"])))
                messages.append((round(end), 0, int(event["pitch"]), 0))
            previous = 0
            for tick, is_on, pitch, velocity in sorted(messages, key=lambda x: (x[0], x[1])):
                track.append(mido.Message("note_on" if is_on else "note_off", note=pitch,
                                          velocity=velocity, time=tick - previous))
                previous = tick
            midi.tracks.append(track)
        safe_id = "".join(character for character in str(proposal["id"])
                          if character.isalnum() or character in "-_") or "proposal"
        path = directory / f"{safe_id}.mid"
        midi.save(path)
        written.append(path)
    return written

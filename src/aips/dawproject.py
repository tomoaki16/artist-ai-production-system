"""DAWproject input adapter producing a DAW-agnostic Music Context."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ET


class DawprojectError(ValueError):
    """Raised when a DAWproject package cannot be parsed safely."""


@dataclass(frozen=True)
class Source:
    kind: str
    path: str
    confidence: float = 1.0


@dataclass(frozen=True)
class MidiNote:
    time_beats: float
    duration_beats: float
    key: int
    velocity: float
    release_velocity: float | None
    channel: int | None
    drum_voice: str | None = None


@dataclass(frozen=True)
class Clip:
    name: str | None
    time_beats: float
    duration_beats: float
    play_start_beats: float
    content_type: str
    asset_path: str | None = None


@dataclass(frozen=True)
class AudioAsset:
    path: str | None
    sample_rate: int | None
    channels: int | None
    duration_seconds: float | None


@dataclass
class TrackContext:
    id: str
    name: str
    content_types: list[str]
    muted: bool
    solo: bool
    selection_status: str = "playback"
    inferred_role: str = "unknown"
    notes: list[MidiNote] = field(default_factory=list)
    clips: list[Clip] = field(default_factory=list)
    audio_assets: list[AudioAsset] = field(default_factory=list)
    source: Source | None = None


GM_DRUMS = {
    35: "kick", 36: "kick", 38: "snare", 40: "snare",
    42: "closed_hi_hat", 44: "pedal_hi_hat", 46: "open_hi_hat",
    41: "low_tom", 43: "low_tom", 45: "mid_tom", 47: "mid_tom",
    48: "high_tom", 50: "high_tom", 49: "crash", 51: "ride",
}


def _float(value: str | None, default: float | None = None) -> float | None:
    return float(value) if value not in (None, "") else default


def _int(value: str | None) -> int | None:
    return int(value) if value not in (None, "") else None


def _bool(value: str | None) -> bool:
    return value == "true"


def _child_value(element: ET.Element, name: str, default: bool = False) -> bool:
    child = element.find(f".//{name}")
    return _bool(child.get("value")) if child is not None else default


def _role(name: str) -> str:
    normalized = name.casefold()
    if "drum" in normalized or "ssd" in normalized:
        return "drums"
    if "bass" in normalized or "ベース" in normalized:
        return "bass"
    if "guitar" in normalized or "gutitar" in normalized or "ギター" in normalized:
        return "guitar"
    if any(word in normalized for word in ("keys", "piano", "presence", "ピアノ")):
        return "keys"
    return "unknown"


def _load_harmony(path: str | Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DawprojectError(f"invalid harmony JSON: {path}") from exc
    events = data.get("events") if isinstance(data, dict) else data
    if not isinstance(events, list):
        raise DawprojectError("harmony JSON must be an array or contain an events array")
    result = []
    for event in events:
        try:
            result.append({"time_beats": float(event["time_beats"]),
                           "duration_beats": float(event["duration_beats"]),
                           "symbol": str(event["symbol"]), "source": "manual", "confidence": 1.0})
        except (KeyError, TypeError, ValueError) as exc:
            raise DawprojectError("each harmony event needs time_beats, duration_beats and symbol") from exc
    return result


def _overlaps(time: float, duration: float, start: float, end: float) -> bool:
    return time < end and time + duration > start


def parse_dawproject(path: str | Path, *, start_bar: int | None = None,
                     bars: int | None = None, harmony_path: str | Path | None = None) -> dict[str, Any]:
    """Parse a DAWproject package and optionally select a bar range."""
    project_path = Path(path)
    try:
        with ZipFile(project_path) as archive:
            try:
                xml_bytes = archive.read("project.xml")
            except KeyError as exc:
                raise DawprojectError("project.xml is missing") from exc
            package_files = set(archive.namelist())
    except (BadZipFile, OSError) as exc:
        raise DawprojectError(f"invalid DAWproject package: {project_path}") from exc
    try:
        root = ET.fromstring(xml_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, ET.ParseError) as exc:
        raise DawprojectError("project.xml is not valid UTF-8 XML") from exc

    app = root.find("./Application")
    tempo = root.find("./Transport/Tempo")
    signature = root.find("./Transport/TimeSignature")
    numerator = _int(signature.get("numerator")) if signature is not None else None
    denominator = _int(signature.get("denominator")) if signature is not None else None
    beats_per_bar = numerator * 4 / denominator if numerator and denominator else None
    if (start_bar is None) != (bars is None):
        raise DawprojectError("start_bar and bars must be supplied together")
    if start_bar is not None and (start_bar < 1 or bars is None or bars < 1):
        raise DawprojectError("start_bar and bars must be positive")
    if start_bar is not None and beats_per_bar is None:
        raise DawprojectError("bar selection requires a valid time signature")
    selection_start = (start_bar - 1) * beats_per_bar if start_bar is not None else None
    selection_end = selection_start + bars * beats_per_bar if selection_start is not None else None

    tracks: dict[str, TrackContext] = {}
    for element in root.findall("./Structure/Track"):
        track_id = element.get("id") or ""
        channel = element.find("./Channel")
        name = element.get("name") or "Unnamed track"
        tracks[track_id] = TrackContext(
            id=track_id, name=name, content_types=(element.get("contentType") or "").split(),
            muted=_child_value(element, "Mute"),
            solo=_bool(channel.get("solo")) if channel is not None else False,
            inferred_role=_role(name), source=Source(kind="dawproject", path="project.xml"),
        )
    any_solo = any(track.solo for track in tracks.values())
    for track in tracks.values():
        track.selection_status = ("muted_candidate" if track.muted else
                                  "playback" if not any_solo or track.solo else "inactive_due_to_solo")

    for lane in root.findall("./Arrangement/Lanes/Lanes"):
        track = tracks.get(lane.get("track") or "")
        if track is None:
            continue
        clips_parent = lane.find("./Clips")
        for clip in clips_parent.findall("./Clip") if clips_parent is not None else []:
            clip_time = _float(clip.get("time"), 0.0) or 0.0
            clip_duration = _float(clip.get("duration"), 0.0) or 0.0
            play_start = _float(clip.get("playStart"), 0.0) or 0.0
            audio = clip.find(".//Audio")
            asset_path = None
            if audio is not None:
                file_element = audio.find("./File")
                asset_path = file_element.get("path") if file_element is not None else None
                if selection_start is None or _overlaps(
                    clip_time, clip_duration, selection_start, selection_end
                ):
                    track.audio_assets.append(AudioAsset(
                        path=asset_path, sample_rate=_int(audio.get("sampleRate")),
                        channels=_int(audio.get("channels")),
                        duration_seconds=_float(audio.get("duration"))))
            content_type = "audio" if audio is not None else "notes" if clip.find(".//Note") is not None else "unknown"
            if selection_start is None or _overlaps(clip_time, clip_duration, selection_start, selection_end):
                track.clips.append(Clip(name=clip.get("name"), time_beats=clip_time,
                                        duration_beats=clip_duration, play_start_beats=play_start,
                                        content_type=content_type, asset_path=asset_path))
            for note in clip.findall(".//Note"):
                note_time = clip_time + float(note.get("time", "0")) - play_start
                note_duration = float(note.get("duration", "0"))
                if selection_start is not None and not _overlaps(note_time, note_duration, selection_start, selection_end):
                    continue
                key = int(note.get("key", "0"))
                track.notes.append(MidiNote(
                    time_beats=note_time, duration_beats=note_duration, key=key,
                    velocity=float(note.get("vel", "0")), release_velocity=_float(note.get("rel")),
                    channel=_int(note.get("channel")),
                    drum_voice=GM_DRUMS.get(key) if track.inferred_role == "drums" else None))

    harmony_events = _load_harmony(harmony_path)
    if selection_start is not None:
        harmony_events = [event for event in harmony_events if _overlaps(
            event["time_beats"], event["duration_beats"], selection_start, selection_end)]
    missing_assets = sorted({asset.path for track in tracks.values() for asset in track.audio_assets
                             if asset.path and asset.path not in package_files})
    return {
        "schema_version": "0.2",
        "source": asdict(Source(kind="dawproject", path=str(project_path))),
        "application": {"name": app.get("name") if app is not None else None,
                        "version": app.get("version") if app is not None else None},
        "transport": {"tempo_bpm": _float(tempo.get("value")) if tempo is not None else None,
                      "time_signature": {"numerator": numerator, "denominator": denominator},
                      "beats_per_bar": beats_per_bar},
        "selection": None if selection_start is None else {
            "start_bar": start_bar, "bars": bars, "start_beats": selection_start,
            "duration_beats": selection_end - selection_start},
        "harmony": {"available": bool(harmony_events), "source": "manual" if harmony_events else None,
                    "confidence": 1.0 if harmony_events else 0.0,
                    "requires_fallback_input": not harmony_events, "events": harmony_events},
        "tracks": [asdict(track) | {"clip_count": len(track.clips)} for track in tracks.values()],
        "diagnostics": {"missing_audio_assets": missing_assets, "track_count": len(tracks)},
    }

"""DAWproject input adapter.

The adapter intentionally emits a DAW-agnostic Music Context. Unknown or
unsupported DAW data stays outside the core model instead of leaking vendor
specific XML structures into downstream components.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
    notes: list[MidiNote] = field(default_factory=list)
    audio_assets: list[AudioAsset] = field(default_factory=list)
    clip_count: int = 0
    source: Source | None = None


def _float(value: str | None) -> float | None:
    return float(value) if value not in (None, "") else None


def _int(value: str | None) -> int | None:
    return int(value) if value not in (None, "") else None


def _bool(value: str | None) -> bool:
    return value == "true"


def _child_value(element: ET.Element, name: str, default: bool = False) -> bool:
    child = element.find(f".//{name}")
    return _bool(child.get("value")) if child is not None else default


def parse_dawproject(path: str | Path) -> dict[str, Any]:
    """Parse a DAWproject file into the initial canonical Music Context."""
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

    tracks: dict[str, TrackContext] = {}
    for element in root.findall("./Structure/Track"):
        track_id = element.get("id") or ""
        channel = element.find("./Channel")
        content_types = (element.get("contentType") or "").split()
        tracks[track_id] = TrackContext(
            id=track_id,
            name=element.get("name") or "Unnamed track",
            content_types=content_types,
            muted=_child_value(element, "Mute"),
            solo=_bool(channel.get("solo")) if channel is not None else False,
            source=Source(kind="dawproject", path="project.xml"),
        )

    for lane in root.findall(".//Arrangement/Lanes/Lanes"):
        track = tracks.get(lane.get("track") or "")
        if track is None:
            continue
        track.clip_count = len(lane.findall(".//Clip"))
        for note in lane.findall(".//Note"):
            track.notes.append(
                MidiNote(
                    time_beats=float(note.get("time", "0")),
                    duration_beats=float(note.get("duration", "0")),
                    key=int(note.get("key", "0")),
                    velocity=float(note.get("vel", "0")),
                    release_velocity=_float(note.get("rel")),
                    channel=_int(note.get("channel")),
                )
            )
        for audio in lane.findall(".//Audio"):
            file_element = audio.find("./File")
            asset_path = file_element.get("path") if file_element is not None else None
            track.audio_assets.append(
                AudioAsset(
                    path=asset_path,
                    sample_rate=_int(audio.get("sampleRate")),
                    channels=_int(audio.get("channels")),
                    duration_seconds=_float(audio.get("duration")),
                )
            )

    chord_elements = root.findall(".//Chord")
    has_harmony_data = bool(chord_elements)
    missing_assets = sorted(
        asset.path
        for track in tracks.values()
        for asset in track.audio_assets
        if asset.path and asset.path not in package_files
    )

    return {
        "schema_version": "0.1",
        "source": asdict(Source(kind="dawproject", path=str(project_path))),
        "application": {
            "name": app.get("name") if app is not None else None,
            "version": app.get("version") if app is not None else None,
        },
        "transport": {
            "tempo_bpm": _float(tempo.get("value")) if tempo is not None else None,
            "time_signature": {
                "numerator": _int(signature.get("numerator")) if signature is not None else None,
                "denominator": _int(signature.get("denominator")) if signature is not None else None,
            },
        },
        "harmony": {
            "available": has_harmony_data,
            "source": "dawproject" if has_harmony_data else None,
            "confidence": 1.0 if has_harmony_data else 0.0,
            "requires_fallback_input": not has_harmony_data,
        },
        "tracks": [asdict(track) for track in tracks.values()],
        "diagnostics": {
            "missing_audio_assets": missing_assets,
            "track_count": len(tracks),
        },
    }

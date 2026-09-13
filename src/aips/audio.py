"""Local audio feature extraction for DAWproject PCM WAV assets."""

from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import math
import json
import wave
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import numpy as np

from .dawproject import DawprojectError


def load_audio_settings(path: str | Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DawprojectError(f"invalid audio analysis settings JSON: {path}") from exc
    items = data.get("audio_analysis") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise DawprojectError("audio settings must contain an audio_analysis array")
    settings = {}
    for item in items:
        track_id = str(item.get("track_id", ""))
        mode = item.get("pitch_mode", "none")
        if not track_id or mode not in {"none", "monophonic"}:
            raise DawprojectError("audio setting needs track_id and valid pitch_mode")
        settings[track_id] = item
    return settings


def _pcm_to_float(raw: bytes, width: int, channels: int) -> np.ndarray:
    if width == 2:
        values = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 3:
        data = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        ints = (data[:, 0].astype(np.int32) | data[:, 1].astype(np.int32) << 8 |
                data[:, 2].astype(np.int32) << 16)
        ints = np.where(ints & 0x800000, ints - 0x1000000, ints)
        values = ints.astype(np.float32) / 8388608.0
    elif width == 4:
        values = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise DawprojectError(f"unsupported PCM sample width: {width * 8} bit")
    return values.reshape(-1, channels).mean(axis=1) if channels > 1 else values


def _midi_note(frequency: float) -> tuple[float, str]:
    midi = 69 + 12 * math.log2(frequency / 440.0)
    names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    rounded = round(midi)
    return midi, f"{names[rounded % 12]}{rounded // 12 - 1}"


def _pyin_note_events(signal: np.ndarray, rate: int) -> tuple[list[dict[str, Any]], list[float]]:
    """Convert pYIN's smoothed monophonic F0 track to conservative note events."""
    import librosa

    hop = 256
    f0, voiced, probability = librosa.pyin(
        signal, fmin=30.0, fmax=500.0, sr=rate,
        frame_length=4096, hop_length=hop, fill_na=np.nan,
    )
    onset_frames = librosa.onset.onset_detect(
        y=signal, sr=rate, hop_length=hop, backtrack=True, units="frames"
    )
    pitch = librosa.hz_to_midi(f0)
    quantized = np.rint(pitch)
    boundaries = {0, len(f0), *(int(x) for x in onset_frames)}
    valid = np.isfinite(quantized) & voiced & (probability >= 0.5)
    previous = None
    for index in range(2, len(quantized) - 2):
        if not valid[index]:
            if valid[index - 1]:
                boundaries.add(index)
            continue
        note = int(quantized[index])
        if previous is not None and note != previous:
            neighborhood = quantized[index:index + 3]
            if np.all(np.isfinite(neighborhood)) and np.all(neighborhood == note):
                boundaries.add(index)
        previous = note
    points = sorted(boundaries)
    events = []
    for start, end in zip(points, points[1:]):
        mask = valid[start:end]
        if mask.sum() < 3:
            continue
        frequencies = f0[start:end][mask]
        probs = probability[start:end][mask]
        median_frequency = float(np.median(frequencies))
        midi, note_name = _midi_note(median_frequency)
        event = {
            "start_seconds": round(start * hop / rate, 4),
            "end_seconds": round(end * hop / rate, 4),
            "duration_seconds": round((end - start) * hop / rate, 4),
            "midi": round(midi), "note": note_name,
            "frequency_hz": round(median_frequency, 2),
            "confidence": round(float(np.median(probs)), 3),
            "engine": "librosa.pyin",
        }
        if event["duration_seconds"] >= 0.06:
            if events and events[-1]["midi"] == event["midi"] and event["start_seconds"] - events[-1]["end_seconds"] <= 0.08:
                events[-1]["end_seconds"] = event["end_seconds"]
                events[-1]["duration_seconds"] = round(events[-1]["end_seconds"] - events[-1]["start_seconds"], 4)
                events[-1]["confidence"] = round((events[-1]["confidence"] + event["confidence"]) / 2, 3)
            else:
                events.append(event)
    return events, [round(float(x * hop / rate), 4) for x in onset_frames]


def analyze_pcm_wav(data: bytes, *, pitch_mode: str = "none") -> dict[str, Any]:
    """Extract conservative, provider-independent features from a PCM WAV."""
    try:
        with wave.open(BytesIO(data), "rb") as wav:
            rate, channels, width, frames = (
                wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()
            )
            signal = _pcm_to_float(wav.readframes(frames), width, channels)
    except (wave.Error, EOFError) as exc:
        raise DawprojectError("audio asset is not a supported PCM WAV") from exc
    if not len(signal):
        return {"duration_seconds": 0.0, "confidence": 0.0}

    frame_size = 2048
    hop = 1024
    starts = np.arange(0, max(1, len(signal) - frame_size + 1), hop)
    if len(starts) > 1200:
        starts = starts[np.linspace(0, len(starts) - 1, 1200, dtype=int)]
    rms = np.array([np.sqrt(np.mean(signal[s:s + frame_size] ** 2) + 1e-12) for s in starts])
    db = 20 * np.log10(rms + 1e-12)
    noise_floor = float(np.percentile(db, 25))
    threshold = -55.0 if float(np.max(db) - noise_floor) < 8.0 else max(-55.0, noise_floor + 8.0)
    active = db > threshold
    rises = np.diff(db, prepend=db[0])
    onset_idx = np.where(active & (rises > 6.0))[0]
    if len(onset_idx):
        keep = np.r_[True, np.diff(starts[onset_idx]) > rate * 0.08]
        onset_idx = onset_idx[keep]

    window = np.hanning(frame_size)
    centroid_values = []
    for s in starts[active][::max(1, int(active.sum() / 80))]:
        chunk = signal[s:s + frame_size]
        if len(chunk) < frame_size:
            continue
        spectrum = np.abs(np.fft.rfft(chunk * window))
        freqs = np.fft.rfftfreq(frame_size, 1 / rate)
        centroid_values.append(float((freqs * spectrum).sum() / (spectrum.sum() + 1e-12)))

    note_events = []
    library_onsets = None
    if pitch_mode == "monophonic":
        note_events, library_onsets = _pyin_note_events(signal, rate)

    pitch_candidates = []
    if note_events:
        total_duration = sum(event["duration_seconds"] for event in note_events)
        midi_notes = [event["midi"] for event in note_events]
        for midi_note in sorted(set(midi_notes), key=lambda n: sum(e["duration_seconds"] for e in note_events if e["midi"] == n), reverse=True)[:5]:
            group = [event for event in note_events if event["midi"] == midi_note]
            pitch_candidates.append({
                "note": group[0]["note"], "midi": midi_note,
                "frequency_hz": round(float(np.median([e["frequency_hz"] for e in group])), 2),
                "duration_share": round(sum(e["duration_seconds"] for e in group) / total_duration, 3),
                "confidence": round(float(np.median([e["confidence"] for e in group])), 3),
            })
    return {
        "duration_seconds": round(len(signal) / rate, 3),
        "sample_rate": rate,
        "channels": channels,
        "dynamics": {"median_dbfs": round(float(np.median(db[active])) if active.any() else -120.0, 2),
                     "peak_dbfs": round(20 * math.log10(float(np.max(np.abs(signal))) + 1e-12), 2)},
        "onsets_seconds": library_onsets if library_onsets is not None else [round(float(starts[i] / rate), 3) for i in onset_idx[:200]],
        "spectral_centroid_hz": round(float(np.median(centroid_values)), 1) if centroid_values else None,
        "pitch_candidates": pitch_candidates,
        "note_events": note_events,
        "pitch_mode": pitch_mode,
        "confidence": 0.8 if active.any() else 0.2,
    }


def _trim_pcm_wav(data: bytes, offset_seconds: float, duration_seconds: float) -> bytes:
    """Return a PCM WAV containing only the range used by a DAW clip."""
    source = BytesIO(data)
    try:
        with wave.open(source, "rb") as wav:
            params = wav.getparams()
            start = min(wav.getnframes(), max(0, round(offset_seconds * wav.getframerate())))
            length = max(0, round(duration_seconds * wav.getframerate()))
            wav.setpos(start)
            frames = wav.readframes(min(length, wav.getnframes() - start))
    except (wave.Error, EOFError) as exc:
        raise DawprojectError("audio asset is not a supported PCM WAV") from exc
    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setparams(params)
        wav.writeframes(frames)
    return output.getvalue()


_NOTE_CLASSES = {name: index for index, name in enumerate(
    ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
)} | {"DB": 1, "EB": 3, "GB": 6, "AB": 8, "BB": 10}


def _chord_tone_role(midi: int, symbol: str) -> str:
    normalized = symbol.strip().upper().replace("♭", "B").replace("♯", "#")
    root_name = normalized[:2] if len(normalized) > 1 and normalized[1] in "#B" else normalized[:1]
    root = _NOTE_CLASSES.get(root_name)
    if root is None:
        return "unknown"
    interval = (midi - root) % 12
    suffix = symbol[len(root_name):]
    minor = suffix.startswith("m") and not suffix.lower().startswith("maj")
    diminished = "DIM" in normalized or "°" in symbol
    roles = {0: "root", 7: "fifth"}
    roles[3 if minor else 4] = "third"
    if diminished:
        roles[3], roles[6] = "third", "diminished_fifth"
    if "MAJ7" in normalized or "M7" in symbol:
        roles[11] = "major_seventh"
    elif "7" in normalized:
        roles[10] = "minor_seventh"
    return roles.get(interval, "non_chord_tone")


def _annotate_harmony(events: list[dict[str, Any]], harmony: list[dict[str, Any]]) -> None:
    for event in events:
        beat = event.get("song_time_beats")
        if beat is None:
            continue
        # A played attack may precede the grid by a few milliseconds. Treat it as
        # belonging to the imminent chord without quantizing the recorded timing.
        harmonic_start = beat + 0.1
        harmonic_end = max(harmonic_start, event.get("song_end_time_beats", beat) - 0.1)
        contexts = [item for item in harmony if
                    item["time_beats"] < harmonic_end and
                    item["time_beats"] + item["duration_beats"] > harmonic_start]
        chord = next((item for item in contexts if
                      item["time_beats"] <= harmonic_start <
                      item["time_beats"] + item["duration_beats"]), None)
        if chord:
            event["chord"] = chord["symbol"]
            event["harmonic_role"] = _chord_tone_role(event["midi"], chord["symbol"])
        event["harmonic_contexts"] = [
            {"chord": item["symbol"],
             "role": _chord_tone_role(event["midi"], item["symbol"])}
            for item in contexts
        ]


def add_local_audio_analysis(dawproject: str | Path, payload: dict[str, Any],
                             settings: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Analyze only Artist-authorized tracks/assets and attach derived features."""
    result = deepcopy(payload)
    with ZipFile(dawproject) as archive:
        for track in result["project"]["tracks"]:
            setting = settings.get(str(track["id"]))
            if not setting or not setting.get("enabled", True):
                continue
            pitch_mode = setting.get("pitch_mode", "none")
            analyses = []
            for clip in track.get("clips", []):
                path = clip.get("asset_path")
                if not path:
                    continue
                try:
                    data = archive.read(path)
                except KeyError as exc:
                    raise DawprojectError(f"audio asset is missing: {path}") from exc
                offset = float(clip.get("audio_offset_seconds") or 0.0)
                duration = clip.get("audio_duration_seconds")
                if duration is not None:
                    data = _trim_pcm_wav(data, offset, float(duration))
                analysis = analyze_pcm_wav(data, pitch_mode=pitch_mode)
                for event in analysis.get("note_events", []):
                    event["song_time_beats"] = round(
                        float(clip["time_beats"]) + event["start_seconds"] *
                        float(result["project"]["transport"]["tempo_bpm"]) / 60.0, 4
                    )
                    event["song_end_time_beats"] = round(
                        float(clip["time_beats"]) + event["end_seconds"] *
                        float(result["project"]["transport"]["tempo_bpm"]) / 60.0, 4
                    )
                _annotate_harmony(
                    analysis.get("note_events", []), result["project"]["harmony"].get("events", [])
                )
                analyses.append({"asset_path": path, "clip_name": clip.get("name"),
                                 "clip_time_beats": clip.get("time_beats"),
                                 "source_offset_seconds": round(offset, 6),
                                 "source": "local_pcm_analysis",
                                 "features": analysis})
            if analyses:
                track["audio_analysis"] = analyses
    return result

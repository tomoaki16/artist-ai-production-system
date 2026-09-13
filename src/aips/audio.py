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

    pitches = []
    if pitch_mode == "monophonic":
        down = max(1, rate // 11025)
        sampled = signal[::down]
        sample_rate = rate / down
        pitch_frame = 4096
        active_starts = starts[active]
        if len(active_starts) > 40:
            active_starts = active_starts[np.linspace(0, len(active_starts) - 1, 40, dtype=int)]
        for original_start in active_starts:
            s = int(original_start / down)
            chunk = sampled[s:s + pitch_frame]
            if len(chunk) < pitch_frame:
                continue
            chunk = (chunk - chunk.mean()) * np.hanning(pitch_frame)
            spectrum = np.fft.rfft(chunk, n=pitch_frame * 2)
            corr = np.fft.irfft(spectrum * np.conj(spectrum))[:pitch_frame]
            minimum, maximum = int(sample_rate / 400), int(sample_rate / 40)
            lag = minimum + int(np.argmax(corr[minimum:maximum]))
            clarity = float(corr[lag] / (corr[0] + 1e-12))
            if clarity > 0.25:
                frequency = sample_rate / lag
                midi, note = _midi_note(frequency)
                pitches.append((midi, frequency, note, clarity))

    pitch_candidates = []
    if pitches:
        rounded_notes = [round(p[0]) for p in pitches]
        for midi_note in sorted(set(rounded_notes), key=lambda n: rounded_notes.count(n), reverse=True)[:5]:
            group = [p for p in pitches if round(p[0]) == midi_note]
            representative = min(group, key=lambda p: abs(p[0] - midi_note))
            pitch_candidates.append({
                "note": representative[2], "midi": midi_note,
                "frequency_hz": round(float(np.median([p[1] for p in group])), 2),
                "frame_share": round(len(group) / len(pitches), 3),
                "confidence": round(float(np.median([p[3] for p in group])), 3),
            })
    return {
        "duration_seconds": round(len(signal) / rate, 3),
        "sample_rate": rate,
        "channels": channels,
        "dynamics": {"median_dbfs": round(float(np.median(db[active])) if active.any() else -120.0, 2),
                     "peak_dbfs": round(20 * math.log10(float(np.max(np.abs(signal))) + 1e-12), 2)},
        "onsets_seconds": [round(float(starts[i] / rate), 3) for i in onset_idx[:200]],
        "spectral_centroid_hz": round(float(np.median(centroid_values)), 1) if centroid_values else None,
        "pitch_candidates": pitch_candidates,
        "pitch_mode": pitch_mode,
        "confidence": 0.8 if active.any() else 0.2,
    }


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
            for asset in track.get("audio_assets", []):
                path = asset.get("path")
                if not path:
                    continue
                try:
                    analysis = analyze_pcm_wav(archive.read(path), pitch_mode=pitch_mode)
                except KeyError as exc:
                    raise DawprojectError(f"audio asset is missing: {path}") from exc
                analyses.append({"asset_path": path, "source": "local_pcm_analysis",
                                 "features": analysis})
            if analyses:
                track["audio_analysis"] = analyses
    return result

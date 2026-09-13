from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile
from io import BytesIO
import math
import struct
import wave

from aips.dawproject import parse_dawproject
from aips.decisions import prepare_ai_payload
from aips.review import render_ai_payload_preview, render_material_review
from aips.audio import add_local_audio_analysis, analyze_pcm_wav


PROJECT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Project version="1.0">
  <Application name="Test DAW" version="1.0"/>
  <Transport>
    <Tempo value="100"/>
    <TimeSignature numerator="4" denominator="4"/>
  </Transport>
  <Structure>
    <Track id="midi" name="Drums" contentType="notes">
      <Channel solo="true"><Mute value="false"/></Channel>
    </Track>
    <Track id="audio" name="Bass" contentType="audio">
      <Channel><Mute value="true"/></Channel>
    </Track>
  </Structure>
  <Arrangement><Lanes>
    <Lanes track="midi"><Clips><Clip name="beat" time="4" duration="4" playStart="1"><Notes>
      <Note time="0" duration="0.25" key="36" vel="0.8" channel="9"/>
      <Note time="2" duration="0.25" key="38" vel="0.7" channel="9"/>
    </Notes></Clip></Clips></Lanes>
    <Lanes track="audio"><Clips><Clip name="take" time="8" duration="4" playStart="0"><Audio sampleRate="44100" channels="1" duration="2.0">
      <File path="audio/bass.wav"/>
    </Audio></Clip></Clips></Lanes>
  </Lanes></Arrangement>
</Project>
"""


class DawprojectAdapterTest(unittest.TestCase):
    def test_parses_midi_audio_and_transport(self) -> None:
        with TemporaryDirectory() as directory:
            package = Path(directory) / "song.dawproject"
            with ZipFile(package, "w") as archive:
                archive.writestr("project.xml", PROJECT_XML)
                archive.writestr("audio/bass.wav", b"test")

            context = parse_dawproject(package)

        self.assertEqual(context["transport"]["tempo_bpm"], 100)
        self.assertEqual(
            context["transport"]["time_signature"],
            {"numerator": 4, "denominator": 4},
        )
        self.assertEqual(context["diagnostics"]["track_count"], 2)
        self.assertEqual(context["diagnostics"]["missing_audio_assets"], [])
        self.assertTrue(context["harmony"]["requires_fallback_input"])
        self.assertEqual(context["tracks"][0]["notes"][0]["key"], 36)
        self.assertEqual(context["tracks"][0]["notes"][0]["time_beats"], 3)
        self.assertEqual(context["tracks"][0]["notes"][0]["drum_voice"], "kick")
        self.assertEqual(context["tracks"][0]["clip_count"], 1)
        self.assertEqual(context["tracks"][0]["selection_status"], "playback")
        self.assertEqual(context["tracks"][1]["selection_status"], "muted_candidate")
        self.assertEqual(
            context["tracks"][1]["audio_assets"][0]["path"], "audio/bass.wav"
        )

    def test_selects_bars_and_merges_manual_harmony(self) -> None:
        with TemporaryDirectory() as directory:
            package = Path(directory) / "song.dawproject"
            harmony = Path(directory) / "harmony.json"
            harmony.write_text(
                '[{"time_beats": 4, "duration_beats": 4, "symbol": "Em"}]',
                encoding="utf-8",
            )
            with ZipFile(package, "w") as archive:
                archive.writestr("project.xml", PROJECT_XML)
                archive.writestr("audio/bass.wav", b"test")
            context = parse_dawproject(
                package, start_bar=2, bars=1, harmony_path=harmony
            )

        self.assertEqual(context["selection"]["start_beats"], 4)
        self.assertEqual(len(context["tracks"][0]["notes"]), 1)
        self.assertEqual(context["tracks"][0]["notes"][0]["key"], 38)
        self.assertEqual(context["harmony"]["events"][0]["symbol"], "Em")

    def test_renders_artist_review_controls(self) -> None:
        with TemporaryDirectory() as directory:
            package = Path(directory) / "song.dawproject"
            with ZipFile(package, "w") as archive:
                archive.writestr("project.xml", PROJECT_XML)
                archive.writestr("audio/bass.wav", b"test")
            html = render_material_review(parse_dawproject(package))

        self.assertIn("AIに渡す素材を確認", html)
        self.assertIn("Drums", html)
        self.assertIn("使う", html)
        self.assertIn("参照", html)
        self.assertIn("無視", html)
        self.assertIn("artist-decisions.json", html)
        self.assertIn('data-value="reference"', html)

    def test_artist_decisions_define_ai_boundary(self) -> None:
        with TemporaryDirectory() as directory:
            package = Path(directory) / "song.dawproject"
            with ZipFile(package, "w") as archive:
                archive.writestr("project.xml", PROJECT_XML)
                archive.writestr("audio/bass.wav", b"test")
            context = parse_dawproject(package)
        decisions = {"track_decisions": [
            {"track_id": "midi", "usage": "use", "role": "drums"},
            {"track_id": "audio", "usage": "ignore", "role": "bass"},
        ]}
        payload = prepare_ai_payload(context, decisions)

        self.assertEqual(payload["artist_authority"]["editable_track_ids"], ["midi"])
        self.assertEqual(len(payload["project"]["tracks"]), 1)
        self.assertEqual(payload["excluded_from_ai"][0]["name"], "Bass")
        preview = render_ai_payload_preview(payload)
        self.assertIn("AIへ渡す内容を確認", preview)
        self.assertIn("変更可能", preview)
        self.assertIn("AIへ送らないトラック：Bass", preview)

    def test_analyzes_pcm_audio_locally(self) -> None:
        buffer = BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            frequencies = [82.4069, 103.826, 110.0, 123.471]
            samples = []
            for frequency in frequencies:
                samples.extend(
                    int(12000 * math.sin(2 * math.pi * frequency * i / 8000))
                    for i in range(8000)
                )
            wav.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
        analysis = analyze_pcm_wav(buffer.getvalue(), pitch_mode="monophonic")

        self.assertEqual(analysis["sample_rate"], 8000)
        self.assertTrue(analysis["pitch_candidates"])
        detected = {event["midi"] for event in analysis["note_events"]}
        self.assertTrue({40, 44, 45, 47}.issubset(detected))
        self.assertEqual(analysis["note_events"][0]["engine"], "librosa.pyin")


if __name__ == "__main__":
    unittest.main()

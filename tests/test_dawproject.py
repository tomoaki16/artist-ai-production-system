from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile
from io import BytesIO
import math
import json
import struct
import wave

from aips.dawproject import parse_dawproject
from aips.decisions import prepare_ai_payload, prepare_producer_request
from aips.review import (render_ai_payload_preview, render_analysis_review,
                         render_material_review, render_proposal_comparison)
from aips.audio import _chord_tone_role, add_local_audio_analysis, analyze_pcm_wav
from aips.providers import create_provider_envelope, validate_producer_response
from aips.connections import ConnectionConfig, build_http_request, extract_provider_response
from aips.midi import export_proposal_midi
from aips.dawproject import DawprojectError


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

    def test_maps_warped_audio_clip_to_source_seconds(self) -> None:
        xml = PROJECT_XML.replace(
            '<Audio sampleRate="44100" channels="1" duration="2.0">',
            '<Warps contentTimeUnit="seconds"><Audio sampleRate="44100" channels="1" duration="20.0">'
        ).replace(
            '<File path="audio/bass.wav"/>\n    </Audio>',
            '<File path="audio/bass.wav"/></Audio><Warp time="0" contentTime="0"/>'
            '<Warp time="20" contentTime="10"/></Warps>'
        ).replace('name="take" time="8" duration="4" playStart="0"',
                  'name="take" time="8" duration="4" playStart="12"')
        with TemporaryDirectory() as directory:
            package = Path(directory) / "song.dawproject"
            with ZipFile(package, "w") as archive:
                archive.writestr("project.xml", xml)
                archive.writestr("audio/bass.wav", b"test")
            context = parse_dawproject(package)
        clip = context["tracks"][1]["clips"][0]
        self.assertEqual(clip["audio_offset_seconds"], 6.0)
        self.assertEqual(clip["audio_duration_seconds"], 2.0)

    def test_labels_harmonic_roles(self) -> None:
        self.assertEqual(_chord_tone_role(40, "E"), "root")
        self.assertEqual(_chord_tone_role(44, "E"), "third")
        self.assertEqual(_chord_tone_role(47, "E"), "fifth")
        self.assertEqual(_chord_tone_role(48, "Am7"), "third")
        self.assertEqual(_chord_tone_role(47, "C#m7"), "minor_seventh")

    def test_renders_artist_readable_bass_analysis(self) -> None:
        payload = {"project": {"transport": {"beats_per_bar": 4}, "tracks": [{
            "role": "bass", "audio_analysis": [{"features": {"note_events": [{
                "song_time_beats": 0.02, "note": "E2", "chord": "E",
                "harmonic_role": "root", "confidence": 0.83,
            }]}}]
        }]}}
        html = render_analysis_review(payload)
        self.assertIn("曲を読む", html)
        self.assertIn("E2", html)
        self.assertIn("ルート", html)
        self.assertIn("コードの土台", html)

    def test_combines_harmony_bass_guitar_and_artist_decisions(self) -> None:
        payload = {"project": {
            "transport": {"beats_per_bar": 4},
            "harmony": {"events": [{"time_beats": 0, "duration_beats": 4, "symbol": "E"}]},
            "tracks": [
                {"role": "bass", "audio_analysis": [{"features": {"note_events": [{
                    "song_time_beats": 0.02, "duration_seconds": 2.0, "midi": 40,
                    "note": "E2", "harmonic_role": "root", "confidence": 0.83,
                }]}}]},
                {"role": "guitar", "audio_analysis": [{"features": {"note_events": [{
                    "song_time_beats": 0.03, "duration_seconds": 2.0, "midi": 52,
                    "note": "E3", "confidence": 0.7,
                }]}}]},
            ],
        }}
        html = render_analysis_review(payload)
        self.assertIn("コード", html)
        self.assertIn("ベース", html)
        self.assertIn("ギター", html)
        self.assertIn("E3", html)
        self.assertIn("固定", html)
        self.assertIn("提案可", html)
        self.assertIn("producer-request.json", html)
        self.assertIn('class="analysis-value"', html)
        self.assertIn("original_value", html)
        self.assertIn("corrected", html)
        self.assertIn("解析内容を確定して次へ", html)
        self.assertIn("Producerに依頼する", html)
        self.assertIn("artist-intent", html)
        self.assertIn("artist-constraints", html)

    def test_builds_producer_request_from_artist_authority(self) -> None:
        confirmed = {"bar_decisions": [{"bar": 13, "parts": {
            "harmony": {"value": "F#m", "authority": "protect"},
            "bass": {"value": "F#2", "authority": "protect"},
            "guitar": {"value": "F#2 · C#3 · A3", "authority": "open"},
        }}]}
        request = prepare_producer_request(confirmed, {
            "artist_intent": "サビ前の期待感を強めたい",
            "constraints": ["音数は増やしすぎない"],
            "proposal_count": 3,
        })
        boundary = request["authority_boundary"]
        self.assertEqual(len(boundary["protected"]), 2)
        self.assertEqual(boundary["editable"][0]["part"], "guitar")
        self.assertEqual(request["artist"]["intent"], "サビ前の期待感を強めたい")
        self.assertTrue(request["artist"]["owns_taste_and_final_decision"])

    def test_provider_envelope_and_response_boundary(self) -> None:
        request = {"authority_boundary": {
            "protected": [{"bar": 13, "part": "bass", "value": "F#2"}],
            "editable": [{"bar": 13, "part": "guitar", "value": "F#2 · C#3 · A3"}],
        }, "requested_output": {"proposal_count": 3}}
        envelope = create_provider_envelope(request)
        self.assertIn("Never modify a protected item.", envelope["non_negotiable_rules"])
        response = {"proposals": [{
            "id": "a", "title": "内声を上げる", "rationale": "期待感を作る",
            "changes": [{"bar": 13, "part": "guitar",
                         "from_value": "F#2 · C#3 · A3",
                         "to_value": "F#2 · C#3 · A#3", "reason": "上声を半音上げる"}],
        }]}
        validated = validate_producer_response(request, response)
        self.assertEqual(validated["status"], "validated")

    def test_rejects_ai_change_to_protected_part(self) -> None:
        request = {"authority_boundary": {
            "protected": [{"bar": 13, "part": "bass", "value": "F#2"}],
            "editable": [{"bar": 13, "part": "guitar", "value": "F#2 C#3 A3"}],
        }, "requested_output": {"proposal_count": 3}}
        response = {"proposals": [{
            "id": "bad", "title": "Bass変更", "rationale": "上昇感",
            "changes": [{"bar": 13, "part": "bass", "from_value": "F#2",
                         "to_value": "G#2", "reason": "上げる"}],
        }]}
        with self.assertRaises(DawprojectError):
            validate_producer_response(request, response)

    def test_builds_secret_safe_provider_requests(self) -> None:
        envelope = {"request": "music"}
        anthropic = build_http_request(
            ConnectionConfig("anthropic", "artist-model", "AIPS_TEST_KEY"),
            envelope, {"AIPS_TEST_KEY": "secret"},
        )
        self.assertEqual(anthropic.full_url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(anthropic.headers["X-api-key"], "secret")
        self.assertNotIn(b"secret", anthropic.data)
        gemini = build_http_request(
            ConnectionConfig("gemini", "artist-model", "AIPS_TEST_KEY"),
            envelope, {"AIPS_TEST_KEY": "secret"},
        )
        self.assertIn(":generateContent", gemini.full_url)
        self.assertEqual(gemini.headers["X-goog-api-key"], "secret")

    def test_extracts_provider_json_without_trusting_it(self) -> None:
        proposal = {"proposals": []}
        anthropic = {"content": [{"type": "text", "text": json.dumps(proposal)}]}
        gemini = {"candidates": [{"content": {"parts": [{"text": json.dumps(proposal)}]}}]}
        self.assertEqual(extract_provider_response("anthropic", anthropic), proposal)
        self.assertEqual(extract_provider_response("gemini", gemini), proposal)

    def test_exports_validated_proposal_as_standard_midi(self) -> None:
        validated = {"proposals": [{
            "id": "idea-a", "title": "上行内声", "midi_events": [
                {"bar": 13, "part": "guitar", "beat": 0, "duration_beats": 1,
                 "pitch": 57, "velocity": 82},
                {"bar": 14, "part": "guitar", "beat": 0, "duration_beats": 1,
                 "pitch": 59, "velocity": 84},
            ],
        }]}
        with TemporaryDirectory() as directory:
            paths = export_proposal_midi(validated, directory, tempo_bpm=90)
            data = paths[0].read_bytes()
        self.assertEqual(data[:4], b"MThd")
        self.assertIn(b"Place at bar 13", data)

    def test_renders_proposal_comparison_with_midi_actions(self) -> None:
        validated = {"proposals": [{
            "id": "idea-a", "title": "上昇ボイシング",
            "rationale": "トップノートを上げる",
            "changes": [{"bar": 13, "part": "guitar", "from_value": "F#m",
                         "to_value": "F#m/A", "reason": "上声の方向感"}],
        }]}
        html = render_proposal_comparison(validated)
        self.assertIn("提案を比較", html)
        self.assertIn("上昇ボイシング", html)
        self.assertIn("midi-takes/idea-a.mid", html)
        self.assertIn("この案を選ぶ", html)


if __name__ == "__main__":
    unittest.main()

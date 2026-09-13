from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from aips.dawproject import parse_dawproject


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
    <Lanes track="midi"><Clips><Clip><Notes>
      <Note time="0" duration="0.25" key="36" vel="0.8" channel="9"/>
    </Notes></Clip></Clips></Lanes>
    <Lanes track="audio"><Clips><Clip><Audio sampleRate="44100" channels="1" duration="2.0">
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
        self.assertEqual(
            context["tracks"][1]["audio_assets"][0]["path"], "audio/bass.wav"
        )


if __name__ == "__main__":
    unittest.main()

"""End-to-end Producer workflow from an Artist request to reviewable MIDI takes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Any

from .connections import ConnectionConfig, call_producer
from .midi import export_proposal_midi
from .review import render_proposal_comparison


def produce_assets(
    config: ConnectionConfig,
    producer_request: dict[str, Any],
    output_dir: str | Path,
    *,
    tempo_bpm: float = 90.0,
    caller: Callable[[ConnectionConfig, dict[str, Any]], dict[str, Any]] = call_producer,
) -> dict[str, Any]:
    """Call the Artist-selected AI and build all locally reviewable artifacts."""
    destination = Path(output_dir)
    midi_dir = destination / "midi-takes"
    destination.mkdir(parents=True, exist_ok=True)

    validated = caller(config, producer_request)
    validated_path = destination / "validated-proposals.json"
    validated_path.write_text(
        json.dumps(validated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    midi_paths = export_proposal_midi(validated, midi_dir, tempo_bpm=tempo_bpm)
    comparison_path = destination / "index.html"
    comparison_path.write_text(
        render_proposal_comparison(validated, "midi-takes"), encoding="utf-8"
    )
    return {
        "comparison": comparison_path,
        "validated_response": validated_path,
        "midi": midi_paths,
    }

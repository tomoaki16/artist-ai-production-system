"""Command-line entry point for early technical validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dawproject import DawprojectError, parse_dawproject
from .decisions import (load_confirmed_analysis, load_decisions, prepare_ai_payload,
                        prepare_producer_request)
from .audio import add_local_audio_analysis, load_audio_settings
from .review import (render_ai_payload_preview, render_analysis_review,
                     render_material_review, render_proposal_comparison)
from .providers import validate_producer_response
from .connections import call_producer, load_connection_config
from .midi import export_proposal_midi


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aips")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser(
        "inspect", help="convert a DAWproject into canonical Music Context JSON"
    )
    inspect_parser.add_argument("input", type=Path)
    inspect_parser.add_argument("--output", "-o", type=Path)
    inspect_parser.add_argument("--start-bar", type=int)
    inspect_parser.add_argument("--bars", type=int)
    inspect_parser.add_argument("--harmony", type=Path, help="manual harmony JSON")
    review_parser = subparsers.add_parser(
        "review", help="create an HTML screen for reviewing imported tracks"
    )
    review_parser.add_argument("input", type=Path)
    review_parser.add_argument("--output", "-o", type=Path, required=True)
    review_parser.add_argument("--start-bar", type=int)
    review_parser.add_argument("--bars", type=int)
    review_parser.add_argument("--harmony", type=Path)
    prepare_parser = subparsers.add_parser(
        "prepare", help="apply Artist decisions and create the AI payload JSON"
    )
    prepare_parser.add_argument("input", type=Path)
    prepare_parser.add_argument("--decisions", type=Path, required=True)
    prepare_parser.add_argument("--output", "-o", type=Path, required=True)
    prepare_parser.add_argument("--preview", type=Path)
    prepare_parser.add_argument("--start-bar", type=int)
    prepare_parser.add_argument("--bars", type=int)
    prepare_parser.add_argument("--harmony", type=Path)
    prepare_parser.add_argument(
        "--audio-settings", type=Path, help="run authorized local WAV analysis"
    )
    analysis_parser = subparsers.add_parser(
        "analysis", help="render analyzed Music Context as an Artist-readable HTML timeline"
    )
    analysis_parser.add_argument("input", type=Path, help="analyzed AI payload JSON")
    analysis_parser.add_argument("--output", "-o", type=Path, required=True)
    request_parser = subparsers.add_parser(
        "request", help="create a provider-neutral AI Producer request"
    )
    request_parser.add_argument("input", type=Path, help="Artist-confirmed analysis JSON")
    request_parser.add_argument("--brief", type=Path, required=True,
                                help="Artist intent and constraints JSON")
    request_parser.add_argument("--output", "-o", type=Path, required=True)
    validate_parser = subparsers.add_parser(
        "validate-response", help="reject AI proposals outside the Artist boundary"
    )
    validate_parser.add_argument("request", type=Path)
    validate_parser.add_argument("response", type=Path)
    validate_parser.add_argument("--output", "-o", type=Path, required=True)
    call_parser = subparsers.add_parser(
        "call", help="send a Producer Request through the user's AI connection"
    )
    call_parser.add_argument("input", type=Path, help="Producer Request JSON")
    call_parser.add_argument("--connection", type=Path, required=True)
    call_parser.add_argument("--output", "-o", type=Path, required=True)
    midi_parser = subparsers.add_parser(
        "export-midi", help="export validated proposals as Standard MIDI Files"
    )
    midi_parser.add_argument("input", type=Path, help="validated proposals JSON")
    midi_parser.add_argument("--output-dir", type=Path, required=True)
    midi_parser.add_argument("--tempo", type=float, default=90.0)
    compare_parser = subparsers.add_parser(
        "compare", help="render validated proposals as an Artist comparison screen"
    )
    compare_parser.add_argument("input", type=Path)
    compare_parser.add_argument("--output", "-o", type=Path, required=True)
    compare_parser.add_argument("--midi-directory", default="midi-takes")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "analysis":
        try:
            payload = json.loads(args.input.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"error: invalid analyzed payload: {args.input}") from exc
        args.output.write_text(render_analysis_review(payload), encoding="utf-8")
        return 0
    if args.command == "request":
        try:
            brief = json.loads(args.brief.read_text(encoding="utf-8"))
            request = prepare_producer_request(load_confirmed_analysis(args.input), brief)
        except (OSError, json.JSONDecodeError, DawprojectError) as exc:
            raise SystemExit(f"error: {exc}") from exc
        args.output.write_text(
            json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return 0
    if args.command == "validate-response":
        try:
            request = json.loads(args.request.read_text(encoding="utf-8"))
            response = json.loads(args.response.read_text(encoding="utf-8"))
            validated = validate_producer_response(request, response)
        except (OSError, json.JSONDecodeError, DawprojectError) as exc:
            raise SystemExit(f"error: {exc}") from exc
        args.output.write_text(
            json.dumps(validated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return 0
    if args.command == "call":
        try:
            request = json.loads(args.input.read_text(encoding="utf-8"))
            validated = call_producer(load_connection_config(str(args.connection)), request)
        except (OSError, json.JSONDecodeError, DawprojectError) as exc:
            raise SystemExit(f"error: {exc}") from exc
        args.output.write_text(
            json.dumps(validated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return 0
    if args.command == "export-midi":
        try:
            validated = json.loads(args.input.read_text(encoding="utf-8"))
            export_proposal_midi(validated, args.output_dir, tempo_bpm=args.tempo)
        except (OSError, json.JSONDecodeError, DawprojectError) as exc:
            raise SystemExit(f"error: {exc}") from exc
        return 0
    if args.command == "compare":
        try:
            validated = json.loads(args.input.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"error: invalid validated proposals: {args.input}") from exc
        args.output.write_text(
            render_proposal_comparison(validated, args.midi_directory), encoding="utf-8"
        )
        return 0
    try:
        context = parse_dawproject(
            args.input,
            start_bar=args.start_bar,
            bars=args.bars,
            harmony_path=args.harmony,
        )
    except DawprojectError as exc:
        raise SystemExit(f"error: {exc}") from exc

    if args.command == "review":
        args.output.write_text(render_material_review(context), encoding="utf-8")
        return 0

    if args.command == "prepare":
        payload = prepare_ai_payload(context, load_decisions(args.decisions))
        if args.audio_settings:
            payload = add_local_audio_analysis(
                args.input, payload, load_audio_settings(args.audio_settings)
            )
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if args.preview:
            args.preview.write_text(render_ai_payload_preview(payload), encoding="utf-8")
        return 0

    rendered = json.dumps(context, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

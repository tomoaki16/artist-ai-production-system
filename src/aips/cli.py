"""Command-line entry point for early technical validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dawproject import DawprojectError, parse_dawproject
from .review import render_material_review


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
    return parser


def main() -> int:
    args = build_parser().parse_args()
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

    rendered = json.dumps(context, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

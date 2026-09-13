"""Command-line entry point for early technical validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dawproject import DawprojectError, parse_dawproject


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aips")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser(
        "inspect", help="convert a DAWproject into canonical Music Context JSON"
    )
    inspect_parser.add_argument("input", type=Path)
    inspect_parser.add_argument("--output", "-o", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        context = parse_dawproject(args.input)
    except DawprojectError as exc:
        raise SystemExit(f"error: {exc}") from exc

    rendered = json.dumps(context, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

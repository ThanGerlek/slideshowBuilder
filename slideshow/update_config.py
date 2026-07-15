#!/usr/bin/env python3
"""Update project config from photos/ without rendering."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sync import sync_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Sync a slideshow JSON/YAML config with images in its photos/ folder. "
            "Adds missing slides (random camera and transition.type), "
            "keeps existing settings, drops missing files, and sorts naturally."
        ),
    )
    parser.add_argument(
        "config",
        type=Path,
        nargs="?",
        default=Path(__file__).resolve().parent / "config.yaml",
        help="Path to config (.json / .yaml / .yml; default: slideshow/config.yaml).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config_path = args.config.resolve()

    if not config_path.exists():
        parser.error(f"Config file not found: {config_path}")

    try:
        added = sync_config(config_path)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    if added:
        print(f"Added {len(added)} photo(s) to {config_path}:")
        for name in added:
            print(f"  + {name}")
    else:
        print(f"Config already up to date: {config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

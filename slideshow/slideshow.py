#!/usr/bin/env python3
"""CLI entry point for the slideshow renderer."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from models import load_project
from renderer import RenderOptions, format_command, render
from sync import sync_config
from validation import ValidationError, validate_project


def _default_output_path(config_path: Path) -> Path:
    return config_path.parent / "output" / "slideshow.mp4"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a slideshow video from a JSON or YAML project file using FFmpeg.",
    )
    parser.add_argument(
        "config",
        type=Path,
        help="Path to the slideshow project config (.json, .yaml, or .yml).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output MP4 path (default: <config_dir>/output/slideshow.mp4).",
    )
    parser.add_argument(
        "--resolution",
        default="1920x1080",
        help="Output resolution as WIDTHxHEIGHT (default: 1920x1080).",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Output frame rate (default: 30).",
    )
    parser.add_argument(
        "--audio",
        type=Path,
        help="Optional background audio file to mix into the slideshow.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the FFmpeg command without executing it.",
    )
    parser.add_argument(
        "--no-filenames",
        action="store_true",
        help="Hide per-slide filename overlays (shown by default).",
    )
    parser.add_argument(
        "--preset",
        default="veryfast",
        help="libx264 encode preset (default: veryfast). Try 'faster' or 'ultrafast' for speed.",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=20,
        help="libx264 quality CRF (default: 20; higher = smaller/faster, lower = better).",
    )
    return parser


def _parse_resolution(value: str) -> tuple[int, int]:
    if "x" not in value:
        raise argparse.ArgumentTypeError("Resolution must be formatted as WIDTHxHEIGHT.")
    width_text, height_text = value.lower().split("x", 1)
    try:
        width = int(width_text)
        height = int(height_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Resolution width and height must be integers.") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("Resolution dimensions must be positive.")
    return width, height


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        width, height = _parse_resolution(args.resolution)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    if args.fps <= 0:
        parser.error("--fps must be a positive integer.")

    config_path = args.config.resolve()
    if not config_path.exists():
        parser.error(f"Config file not found: {config_path}")

    try:
        added = sync_config(config_path)
        if added:
            print(f"Added {len(added)} photo(s) to config: {', '.join(added)}")
        project = load_project(config_path)
        validate_project(project)
    except (ValueError, ValidationError) as exc:
        print(exc, file=sys.stderr)
        return 1

    output_path = (args.output or _default_output_path(config_path)).resolve()
    opts = RenderOptions(
        width=width,
        height=height,
        fps=args.fps,
        audio=args.audio.resolve() if args.audio else None,
        dry_run=args.dry_run,
        show_filenames=not args.no_filenames,
        encode_preset=args.preset,
        crf=args.crf,
    )

    if opts.audio is not None and not opts.audio.exists():
        print(f"Audio file not found: {opts.audio}", file=sys.stderr)
        return 1

    try:
        command = render(project, output_path, opts)
    except (RuntimeError, subprocess.CalledProcessError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    if opts.dry_run:
        print(format_command(command))
        return 0

    print(f"Rendered slideshow to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

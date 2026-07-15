"""Sync project config slides from photos/ before rendering."""

from __future__ import annotations

import random
import re
from pathlib import Path
from typing import Any

from config_io import load_config_dict, save_config_dict
from models import CAMERA_PRESETS, XFADE_TRANSITIONS

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff", ".bmp"})

# Prefer commonly useful xfade types for random assignment.
RANDOM_TRANSITIONS: tuple[str, ...] = tuple(
    sorted(
        name
        for name in XFADE_TRANSITIONS
        if name
        in {
            "fade",
            "fadeblack",
            "fadewhite",
            "dissolve",
            "wipeleft",
            "wiperight",
            "wipeup",
            "wipedown",
            "slideleft",
            "slideright",
            "slideup",
            "slidedown",
            "smoothleft",
            "smoothright",
            "smoothup",
            "smoothdown",
            "circleopen",
            "circleclose",
            "radial",
            "diagtl",
            "diagtr",
            "diagbl",
            "diagbr",
        }
    )
)

CAMERA_CHOICES: tuple[str, ...] = tuple(sorted(CAMERA_PRESETS))


def _natural_key(name: str) -> list[tuple[int, int | str]]:
    """Sort key so '1_...' comes before '12_...'."""
    parts: list[tuple[int, int | str]] = []
    for part in re.split(r"(\d+)", name):
        if not part:
            continue
        if part.isdigit():
            parts.append((0, int(part)))
        else:
            parts.append((1, part.casefold()))
    return parts


def list_photo_filenames(photos_dir: Path) -> list[str]:
    if not photos_dir.is_dir():
        return []
    names = [path.name for path in photos_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS]
    names.sort(key=_natural_key)
    return names


def _new_slide(filename: str) -> dict[str, Any]:
    return {
        "file": filename,
        "camera": random.choice(CAMERA_CHOICES),
        "transition": {
            "type": random.choice(RANDOM_TRANSITIONS),
        },
    }


def sync_config(config_path: Path) -> list[str]:
    """
    Ensure every image in photos/ has a slide entry.

    Existing slide settings are kept. New slides get random camera and
    transition.type only (duration fields inherit from defaults). The slides
    list is rewritten in natural alphanumeric filename order.

    Returns filenames that were newly added.
    """
    config_path = config_path.resolve()
    data = load_config_dict(config_path)

    photos_dir = config_path.parent / "photos"
    photo_names = list_photo_filenames(photos_dir)
    if not photo_names:
        raise ValueError(f"No images found in {photos_dir}")

    raw_slides = data.get("slides", [])
    if raw_slides is None:
        raw_slides = []
    if not isinstance(raw_slides, list):
        raise ValueError("'slides' must be a list.")

    by_file: dict[str, dict[str, Any]] = {}
    for raw in raw_slides:
        if isinstance(raw, dict) and isinstance(raw.get("file"), str):
            by_file[raw["file"]] = raw

    added: list[str] = []
    synced: list[dict[str, Any]] = []
    for name in photo_names:
        if name in by_file:
            synced.append(by_file[name])
        else:
            slide = _new_slide(name)
            synced.append(slide)
            added.append(name)

    data["slides"] = synced
    save_config_dict(config_path, data)

    return added

"""Data models and project config loading for slideshow projects."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from camera_math import (
    DEFAULT_Z_FAR,
    DEFAULT_Z_NEAR,
    DEFAULT_Z_STATIC,
    Corner,
    KenBurnsMode,
    PanDirection,
    PresetIntent,
)
from config_io import load_config_dict

# Far / near zooms sized so Box(z) has non-degenerate pan room.
_ZF = DEFAULT_Z_FAR
_ZN = DEFAULT_Z_NEAR


# Public preset names → trajectory intent (endpoints resolved per image).
CAMERA_PRESETS: dict[str, PresetIntent] = {
    "static": PresetIntent(z_start=DEFAULT_Z_STATIC, z_end=DEFAULT_Z_STATIC),
    "zoom-in": PresetIntent(z_start=_ZF, z_end=_ZN),
    "zoom-out": PresetIntent(z_start=_ZN, z_end=_ZF),
    "pan-left": PresetIntent(z_start=_ZN, z_end=_ZN, pan=PanDirection.LEFT),
    "pan-right": PresetIntent(z_start=_ZN, z_end=_ZN, pan=PanDirection.RIGHT),
    "pan-up": PresetIntent(z_start=_ZN, z_end=_ZN, pan=PanDirection.UP),
    "pan-down": PresetIntent(z_start=_ZN, z_end=_ZN, pan=PanDirection.DOWN),
    # Documentary drift: BR corner → center while zooming in.
    "kenburns": PresetIntent(
        z_start=_ZF,
        z_end=_ZN,
        kenburns=KenBurnsMode.CORNER_TO_CENTER,
        corner=Corner.BR,
    ),
    # Reverse: center → TL while zooming out (zoom-out feel with drift).
    "kenburns-reverse": PresetIntent(
        z_start=_ZN,
        z_end=_ZF,
        kenburns=KenBurnsMode.CENTER_TO_CORNER,
        corner=Corner.TL,
    ),
}

DEFAULT_CAMERA = "zoom-in"

XFADE_TRANSITIONS: frozenset[str] = frozenset(
    {
        "fade",
        "wipeleft",
        "wiperight",
        "wipeup",
        "wipedown",
        "distance",
        "radial",
        "smoothleft",
        "smoothright",
        "smoothup",
        "smoothdown",
        "circleopen",
        "circleclose",
        "vertopen",
        "vertclose",
        "horzopen",
        "horzclose",
        "dissolve",
        "pixelize",
        "diagtl",
        "diagtr",
        "diagbl",
        "diagbr",
        "hlslice",
        "hrslice",
        "vuslice",
        "vdslice",
        "hblur",
        "fadegrays",
    }
)


@dataclass
class Transition:
    type: str
    duration: float


@dataclass
class Slide:
    file: Path
    duration: float
    camera: str
    transition: Transition

    def camera_intent(self) -> PresetIntent:
        try:
            return CAMERA_PRESETS[self.camera]
        except KeyError as exc:
            raise ValueError(f"Unknown camera preset: {self.camera!r}") from exc


@dataclass
class Defaults:
    duration: float = 4.0
    transition: Transition = field(default_factory=lambda: Transition(type="fade", duration=1.0))
    camera: str = DEFAULT_CAMERA


@dataclass
class Project:
    slides: list[Slide]
    defaults: Defaults = field(default_factory=Defaults)
    project_dir: Path = field(default_factory=Path.cwd)

    @property
    def photos_dir(self) -> Path:
        return self.project_dir / "photos"

    def total_duration(self) -> float:
        if not self.slides:
            return 0.0
        total = sum(slide.duration for slide in self.slides)
        overlap = sum(slide.transition.duration for slide in self.slides[:-1])
        return total - overlap


def _parse_camera(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    if not isinstance(value, str):
        raise ValueError(f"camera must be a preset name string (one of: {', '.join(sorted(CAMERA_PRESETS))})")
    return value


def _parse_transition(data: dict[str, Any] | None, fallback: Transition) -> Transition:
    if not data:
        return fallback
    return Transition(
        type=data.get("type", fallback.type),
        duration=float(data.get("duration", fallback.duration)),
    )


def _parse_defaults(data: dict[str, Any] | None) -> Defaults:
    defaults = Defaults()
    if not data:
        return defaults
    return Defaults(
        duration=float(data.get("duration", defaults.duration)),
        transition=_parse_transition(data.get("transition"), defaults.transition),
        camera=_parse_camera(data.get("camera"), defaults.camera),
    )


def _merge_slide(raw: dict[str, Any], defaults: Defaults, project_dir: Path) -> Slide:
    if "file" not in raw:
        raise ValueError("Each slide must include a 'file' field.")
    return Slide(
        file=project_dir / "photos" / raw["file"],
        duration=float(raw.get("duration", defaults.duration)),
        camera=_parse_camera(raw.get("camera"), defaults.camera),
        transition=_parse_transition(raw.get("transition"), defaults.transition),
    )


def load_project(config_path: Path) -> Project:
    config_path = config_path.resolve()
    data = load_config_dict(config_path)

    defaults = _parse_defaults(data.get("defaults"))
    raw_slides = data.get("slides", [])
    if not isinstance(raw_slides, list):
        raise ValueError("'slides' must be a list.")

    project_dir = config_path.parent
    slides = [_merge_slide(raw, defaults, project_dir) for raw in raw_slides]
    return Project(slides=slides, defaults=defaults, project_dir=project_dir)

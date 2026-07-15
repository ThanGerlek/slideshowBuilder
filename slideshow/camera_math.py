"""Cover-fit pan/zoom geometry, distance metrics, and preset resolution.

Implements the model in pan-and-zoom-math.md: crop-window centers (u, v),
Box(z) feasible pan region, ease-in-out trajectories, and §7C speed clamping.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

# Defaults from the math doc / standardization plan.
DEFAULT_V_TARGET = 40.0  # viewport-scale pixels per second
DEFAULT_Z_FAR = 1.05
DEFAULT_Z_NEAR = 1.15
DEFAULT_Z_STATIC = 1.06
ZOOM_DISTANCE_K = 1.0


class PanDirection(Enum):
    LEFT = "left"  # center moves left (decreasing u)
    RIGHT = "right"
    UP = "up"  # center moves up (decreasing v)
    DOWN = "down"


class KenBurnsMode(Enum):
    CORNER_TO_CENTER = "corner_to_center"  # zoom in while drifting
    CENTER_TO_CORNER = "center_to_corner"  # zoom out while drifting


class Corner(Enum):
    TL = "tl"
    TR = "tr"
    BL = "bl"
    BR = "br"


@dataclass(frozen=True)
class PresetIntent:
    """Named camera intent — endpoints are solved per image."""

    z_start: float
    z_end: float
    pan: PanDirection | None = None
    kenburns: KenBurnsMode | None = None
    corner: Corner | None = None


@dataclass(frozen=True)
class ResolvedCamera:
    """Crop-center trajectory in normalized image space."""

    u_start: float
    v_start: float
    u_end: float
    v_end: float
    zoom_start: float
    zoom_end: float


@dataclass(frozen=True)
class Box:
    """Feasible normalized crop-center region at a given zoom."""

    u_min: float
    u_max: float
    v_min: float
    v_max: float

    def clamp(self, u: float, v: float) -> tuple[float, float]:
        return (
            min(max(u, self.u_min), self.u_max),
            min(max(v, self.v_min), self.v_max),
        )

    @property
    def width(self) -> float:
        return max(0.0, self.u_max - self.u_min)

    @property
    def height(self) -> float:
        return max(0.0, self.v_max - self.v_min)


def cover_scale(width: float, height: float, viewport_w: float, viewport_h: float) -> float:
    """Smallest scale that covers the viewport (CSS background-size: cover)."""
    if width <= 0 or height <= 0:
        raise ValueError("Image dimensions must be positive")
    return max(viewport_w / width, viewport_h / height)


def window_size(
    zoom: float,
    s_cover: float,
    viewport_w: float,
    viewport_h: float,
) -> tuple[float, float]:
    """Crop window size in image pixels at zoom z ≥ 1."""
    if zoom <= 0 or s_cover <= 0:
        raise ValueError("zoom and s_cover must be positive")
    return viewport_w / (s_cover * zoom), viewport_h / (s_cover * zoom)


def margins(
    zoom: float,
    width: float,
    height: float,
    viewport_w: float,
    viewport_h: float,
) -> tuple[float, float]:
    """Normalized half-window margins mx, my at zoom z."""
    s = cover_scale(width, height, viewport_w, viewport_h)
    w, h = window_size(zoom, s, viewport_w, viewport_h)
    return w / (2.0 * width), h / (2.0 * height)


def feasible_box(
    zoom: float,
    width: float,
    height: float,
    viewport_w: float,
    viewport_h: float,
) -> Box:
    """Box(z): feasible (u, v) crop centers. Degenerate axes collapse to 0.5."""
    mx, my = margins(zoom, width, height, viewport_w, viewport_h)
    if mx >= 0.5:
        u_min = u_max = 0.5
    else:
        u_min, u_max = mx, 1.0 - mx
    if my >= 0.5:
        v_min = v_max = 0.5
    else:
        v_min, v_max = my, 1.0 - my
    return Box(u_min, u_max, v_min, v_max)


def screen_scale(zoom: float, s_cover: float) -> float:
    return s_cover * zoom


def box_max_distance(
    zoom: float,
    width: float,
    height: float,
    viewport_w: float,
    viewport_h: float,
) -> float:
    """Farthest pan between two valid centers at z, in screen pixels (§8)."""
    s = cover_scale(width, height, viewport_w, viewport_h)
    mx, my = margins(zoom, width, height, viewport_w, viewport_h)
    box_w = max(0.0, (1.0 - 2.0 * mx) * width)
    box_h = max(0.0, (1.0 - 2.0 * my) * height)
    return screen_scale(zoom, s) * math.hypot(box_w, box_h)


def pan_zoom_distance(
    u0: float,
    v0: float,
    u1: float,
    v1: float,
    z0: float,
    z1: float,
    width: float,
    height: float,
    viewport_w: float,
    viewport_h: float,
    k: float = ZOOM_DISTANCE_K,
) -> float:
    """Unified travel distance in screen pixels (§6)."""
    s_cover = cover_scale(width, height, viewport_w, viewport_h)
    z_avg = (z0 + z1) / 2.0
    pan_d = screen_scale(z_avg, s_cover) * math.hypot((u1 - u0) * width, (v1 - v0) * height)
    diag = math.hypot(viewport_w, viewport_h)
    if z0 <= 0 or z1 <= 0:
        zoom_d = 0.0
    else:
        zoom_d = k * diag * abs(math.log(z1 / z0))
    return math.hypot(pan_d, zoom_d)


def ease_smoothstep(tau: float) -> float:
    """Ease-in-out cubic: 3τ² − 2τ³."""
    t = min(max(tau, 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def capped_image_size(width: int, height: int, max_edge: int) -> tuple[int, int]:
    """Match FFmpeg scale=min(iw,MAX):min(ih,MAX):force_original_aspect_ratio=decrease."""
    if width <= 0 or height <= 0:
        raise ValueError("Image dimensions must be positive")
    if max(width, height) <= max_edge:
        return width, height
    factor = max_edge / max(width, height)
    return max(1, int(width * factor)), max(1, int(height * factor))


def _corner_uv(box: Box, corner: Corner) -> tuple[float, float]:
    if corner is Corner.TL:
        return box.u_min, box.v_min
    if corner is Corner.TR:
        return box.u_max, box.v_min
    if corner is Corner.BL:
        return box.u_min, box.v_max
    return box.u_max, box.v_max


def _scale_segment_to_distance(
    u0: float,
    v0: float,
    u1: float,
    v1: float,
    z0: float,
    z1: float,
    width: float,
    height: float,
    viewport_w: float,
    viewport_h: float,
    target_distance: float,
) -> tuple[float, float, float, float, float, float]:
    """Shrink pan and/or zoom endpoints so total_distance ≤ target_distance."""
    current = pan_zoom_distance(u0, v0, u1, v1, z0, z1, width, height, viewport_w, viewport_h)
    if current <= target_distance or current <= 1e-9:
        return u0, v0, u1, v1, z0, z1

    # Binary-search a blend factor t in [0,1]: t=1 is full motion, t=0 is none.
    lo, hi = 0.0, 1.0
    best = (u0, v0, u0, v0, z0, z0)
    for _ in range(40):
        mid = (lo + hi) / 2.0
        um = u0 + (u1 - u0) * mid
        vm = v0 + (v1 - v0) * mid
        zm = z0 + (z1 - z0) * mid
        dist = pan_zoom_distance(u0, v0, um, vm, z0, zm, width, height, viewport_w, viewport_h)
        if dist <= target_distance:
            best = (u0, v0, um, vm, z0, zm)
            lo = mid
        else:
            hi = mid
    return best


def _resolve_pan(
    direction: PanDirection,
    zoom: float,
    width: float,
    height: float,
    viewport_w: float,
    viewport_h: float,
    duration: float,
    v_target: float,
) -> ResolvedCamera:
    box = feasible_box(zoom, width, height, viewport_w, viewport_h)
    desired = v_target * duration
    max_d = box_max_distance(zoom, width, height, viewport_w, viewport_h)
    actual = min(desired, max_d)

    s = cover_scale(width, height, viewport_w, viewport_h)
    s_z = screen_scale(zoom, s)

    if direction in (PanDirection.LEFT, PanDirection.RIGHT):
        # Full axis span in normalized u; v fixed at center.
        u_lo, u_hi = box.u_min, box.u_max
        if direction is PanDirection.RIGHT:
            u0, u1 = u_lo, u_hi
        else:
            u0, u1 = u_hi, u_lo
        # Screen pan per unit Δu.
        pan_per_u = s_z * width
        if pan_per_u <= 1e-9 or actual <= 1e-9 or abs(u1 - u0) <= 1e-12:
            return ResolvedCamera(0.5, 0.5, 0.5, 0.5, zoom, zoom)
        r_max = abs(u1 - u0)
        r_used = min(r_max, actual / pan_per_u)
        sign = 1.0 if u1 > u0 else -1.0
        return ResolvedCamera(u0, 0.5, u0 + sign * r_used, 0.5, zoom, zoom)

    v_lo, v_hi = box.v_min, box.v_max
    if direction is PanDirection.DOWN:
        v0, v1 = v_lo, v_hi
    else:
        v0, v1 = v_hi, v_lo
    pan_per_v = s_z * height
    if pan_per_v <= 1e-9 or actual <= 1e-9 or abs(v1 - v0) <= 1e-12:
        return ResolvedCamera(0.5, 0.5, 0.5, 0.5, zoom, zoom)
    r_max = abs(v1 - v0)
    r_used = min(r_max, actual / pan_per_v)
    sign = 1.0 if v1 > v0 else -1.0
    return ResolvedCamera(0.5, v0, 0.5, v0 + sign * r_used, zoom, zoom)


def _resolve_zoom(
    z_start: float,
    z_end: float,
    width: float,
    height: float,
    viewport_w: float,
    viewport_h: float,
    duration: float,
    v_target: float,
) -> ResolvedCamera:
    desired = v_target * duration
    u0, v0, u1, v1, z0, z1 = _scale_segment_to_distance(
        0.5,
        0.5,
        0.5,
        0.5,
        z_start,
        z_end,
        width,
        height,
        viewport_w,
        viewport_h,
        desired,
    )
    return ResolvedCamera(u0, v0, u1, v1, z0, z1)


def _resolve_kenburns(
    mode: KenBurnsMode,
    corner: Corner,
    z_start: float,
    z_end: float,
    width: float,
    height: float,
    viewport_w: float,
    viewport_h: float,
    duration: float,
    v_target: float,
) -> ResolvedCamera:
    z_min = min(z_start, z_end)
    box = feasible_box(z_min, width, height, viewport_w, viewport_h)
    corner_uv = _corner_uv(box, corner)
    center = (0.5, 0.5)

    if mode is KenBurnsMode.CORNER_TO_CENTER:
        u0, v0 = corner_uv
        u1, v1 = center
    else:
        u0, v0 = center
        u1, v1 = corner_uv

    desired = v_target * duration
    max_d = box_max_distance(z_min, width, height, viewport_w, viewport_h)
    # Combined preset can also spend budget on zoom; cap by hypot of max pan and full zoom.
    full = pan_zoom_distance(u0, v0, u1, v1, z_start, z_end, width, height, viewport_w, viewport_h)
    # Don't travel farther than the box diagonal in pan terms warrants when zoom is small;
    # use min of desired and the geometric full path (full already respects Box endpoints).
    target = min(desired, full if full > 0 else desired)
    # Also respect box diagonal as a soft pan ceiling when zoom delta is tiny.
    if abs(z_end - z_start) < 1e-9:
        target = min(target, max_d)

    u0, v0, u1, v1, z0, z1 = _scale_segment_to_distance(
        u0,
        v0,
        u1,
        v1,
        z_start,
        z_end,
        width,
        height,
        viewport_w,
        viewport_h,
        target,
    )
    return ResolvedCamera(u0, v0, u1, v1, z0, z1)


def resolve_preset(
    intent: PresetIntent,
    width: float,
    height: float,
    viewport_w: float,
    viewport_h: float,
    duration: float,
    v_target: float = DEFAULT_V_TARGET,
) -> ResolvedCamera:
    """Solve aspect-aware endpoints for a preset intent (§7C / §11)."""
    if duration <= 0:
        raise ValueError("duration must be positive")

    if intent.pan is not None:
        z = min(intent.z_start, intent.z_end)
        return _resolve_pan(
            intent.pan,
            z,
            width,
            height,
            viewport_w,
            viewport_h,
            duration,
            v_target,
        )

    if intent.kenburns is not None:
        corner = intent.corner or Corner.BR
        return _resolve_kenburns(
            intent.kenburns,
            corner,
            intent.z_start,
            intent.z_end,
            width,
            height,
            viewport_w,
            viewport_h,
            duration,
            v_target,
        )

    # Static or pure zoom at center.
    if abs(intent.z_end - intent.z_start) < 1e-12:
        return ResolvedCamera(0.5, 0.5, 0.5, 0.5, intent.z_start, intent.z_end)

    return _resolve_zoom(
        intent.z_start,
        intent.z_end,
        width,
        height,
        viewport_w,
        viewport_h,
        duration,
        v_target,
    )


def ffmpeg_smoothstep_expr(progress_expr: str) -> str:
    """FFmpeg expression for smoothstep(progress)."""
    # 3τ² − 2τ³
    return f"(3*pow({progress_expr}\\,2)-2*pow({progress_expr}\\,3))"


def crop_center_to_ffmpeg_xy(
    u_expr: str,
    v_expr: str,
    viewport_w: int,
    viewport_h: int,
) -> tuple[str, str]:
    """Crop top-left from animated center on a scale-to-cover frame (iw/ih post-scale)."""
    # Clamp for even-dimension trunc rounding so crop never exits the frame.
    x_expr = f"max(0\\,min(({u_expr})*iw-({viewport_w}/2)\\,iw-{viewport_w}))"
    y_expr = f"max(0\\,min(({v_expr})*ih-({viewport_h}/2)\\,ih-{viewport_h}))"
    return x_expr, y_expr

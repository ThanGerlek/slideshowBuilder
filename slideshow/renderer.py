"""FFmpeg filter graph construction and rendering."""

from __future__ import annotations

import shlex
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from camera_math import (
    DEFAULT_V_TARGET,
    ResolvedCamera,
    capped_image_size,
    crop_center_to_ffmpeg_xy,
    ffmpeg_smoothstep_expr,
    resolve_preset,
)
from labels import render_label_png
from models import Project, Slide

# Cap source long-edge before Ken Burns work (cuts cost on 6000px+ photos).
MAX_SOURCE_EDGE = 2560
# Parallel slide encodes (I/O + CPU bound).
MAX_SLIDE_WORKERS = 4


@dataclass
class RenderOptions:
    width: int = 1920
    height: int = 1080
    fps: int = 30
    audio: Path | None = None
    dry_run: bool = False
    show_filenames: bool = True
    # libx264 preset: ultrafast / veryfast / faster / fast / medium / ...
    encode_preset: str = "veryfast"
    crf: int = 20
    # Target perceived camera speed in viewport pixels / second (§7C).
    v_target: float = DEFAULT_V_TARGET


@lru_cache(maxsize=256)
def _probe_image_size(path: str) -> tuple[int, int]:
    """Return (width, height) via ffprobe."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise RuntimeError("ffprobe not found on PATH (install FFmpeg).")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    text = result.stdout.strip()
    if "x" not in text:
        raise RuntimeError(f"Could not probe image size for {path!r}: {text!r}")
    width_text, height_text = text.split("x", 1)
    return int(width_text), int(height_text)


def _resolve_slide_camera(slide: Slide, opts: RenderOptions) -> ResolvedCamera:
    """Probe dimensions (after MAX_SOURCE_EDGE cap) and resolve preset endpoints."""
    raw_w, raw_h = _probe_image_size(str(slide.file.resolve()))
    width, height = capped_image_size(raw_w, raw_h, MAX_SOURCE_EDGE)
    return resolve_preset(
        slide.camera_intent(),
        width,
        height,
        opts.width,
        opts.height,
        slide.duration,
        opts.v_target,
    )


def _slide_filter(slide: Slide, index: int, opts: RenderOptions, out_label: str) -> str:
    """Ken Burns via cover-scale + animated center crop (single slide input)."""
    frames = max(int(round(slide.duration * opts.fps)), 1)
    denom = max(frames - 1, 1)
    progress = f"n/{denom}"
    ease = ffmpeg_smoothstep_expr(progress)
    motion = _resolve_slide_camera(slide, opts)
    w, h = opts.width, opts.height

    z_expr = f"{motion.zoom_start}+({motion.zoom_end}-{motion.zoom_start})*({ease})"
    # Cover-fit scale without OVERSCALE — pan room comes from Box(z) / aspect slack.
    cover = f"max({w}*({z_expr})/iw\\,{h}*({z_expr})/ih)"
    u_expr = f"({motion.u_start})+({motion.u_end}-{motion.u_start})*({ease})"
    v_expr = f"({motion.v_start})+({motion.v_end}-{motion.v_start})*({ease})"
    x_expr, y_expr = crop_center_to_ffmpeg_xy(u_expr, v_expr, w, h)

    return (
        f"[{index}:v]"
        f"scale="
        f"'min(iw\\,{MAX_SOURCE_EDGE})':"
        f"'min(ih\\,{MAX_SOURCE_EDGE})':"
        f"force_original_aspect_ratio=decrease:"
        f"flags=fast_bilinear,"
        f"scale="
        f"w='trunc(iw*({cover})/2)*2':"
        f"h='trunc(ih*({cover})/2)*2':"
        f"eval=frame:"
        f"flags=bilinear,"
        f"crop={w}:{h}:"
        f"x='{x_expr}':"
        f"y='{y_expr}',"
        f"setsar=1,"
        f"format=yuv420p"
        f"[{out_label}]"
    )


def _xfade_offsets(slides: list[Slide]) -> list[float]:
    offsets: list[float] = []
    cumulative = 0.0
    for slide in slides[:-1]:
        cumulative += slide.duration
        cumulative -= slide.transition.duration
        offsets.append(cumulative)
    return offsets


def _label_time_windows(slides: list[Slide]) -> list[tuple[float, float]]:
    """Per-slide [start, end) times on the final timeline (switch mid-transition)."""
    total = sum(slide.duration for slide in slides)
    if len(slides) == 1:
        return [(0.0, total)]

    total -= sum(slide.transition.duration for slide in slides[:-1])
    offsets = _xfade_offsets(slides)
    boundaries = [0.0]
    for index, offset in enumerate(offsets):
        boundaries.append(offset + slides[index].transition.duration / 2.0)
    boundaries.append(total)
    return list(zip(boundaries[:-1], boundaries[1:]))


def _encode_args(opts: RenderOptions) -> list[str]:
    return [
        "-c:v",
        "libx264",
        "-preset",
        opts.encode_preset,
        "-crf",
        str(opts.crf),
        "-pix_fmt",
        "yuv420p",
        "-tune",
        "stillimage",
    ]


def build_slide_clip_command(
    slide: Slide,
    output_path: Path,
    opts: RenderOptions,
) -> list[str]:
    """Command that renders one slide's camera motion to a clip."""
    filt = _slide_filter(slide, 0, opts, "vout")
    return [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-loop",
        "1",
        "-framerate",
        str(opts.fps),
        "-t",
        f"{slide.duration:.6f}",
        "-i",
        str(slide.file),
        "-filter_complex",
        filt,
        "-map",
        "[vout]",
        *_encode_args(opts),
        "-an",
        str(output_path),
    ]


def build_compose_command(
    project: Project,
    clip_paths: list[Path],
    output_path: Path,
    opts: RenderOptions,
    label_paths: list[Path] | None = None,
) -> list[str]:
    """Second-pass command: xfade clips, then optional filename overlays."""
    slides = project.slides
    show_labels = bool(label_paths) and opts.show_filenames
    total_duration = project.total_duration()

    input_args: list[str] = []
    for path in clip_paths:
        input_args.extend(["-i", str(path)])

    label_start: int | None = None
    if show_labels and label_paths is not None:
        label_start = len(clip_paths)
        for path in label_paths:
            input_args.extend(
                [
                    "-loop",
                    "1",
                    "-framerate",
                    str(opts.fps),
                    "-t",
                    f"{total_duration:.6f}",
                    "-i",
                    str(path),
                ]
            )

    audio_input_index: int | None = None
    if opts.audio is not None:
        audio_input_index = len(clip_paths) + (len(slides) if show_labels else 0)
        input_args.extend(["-i", str(opts.audio)])

    filters: list[str] = []
    if len(slides) == 1:
        composed = "0:v"
        # No filters yet; may still overlay labels.
        current_video = "[0:v]"
        if not show_labels:
            # Map input directly; add a null filter for a consistent label.
            filters.append("[0:v]null[vout]")
            composed = "vout"
            current_video = "[vout]"
        else:
            composed = "vout"
            filters.append("[0:v]null[vout]")
            current_video = "[vout]"
    else:
        offsets = _xfade_offsets(slides)
        current = "[0:v]"
        for index in range(1, len(slides)):
            transition = slides[index - 1].transition
            next_label = f"[vx{index}]" if index < len(slides) - 1 else "[vout]"
            filters.append(
                f"{current}[{index}:v]"
                f"xfade=transition={transition.type}:"
                f"duration={transition.duration:.6f}:"
                f"offset={offsets[index - 1]:.6f}"
                f"{next_label}"
            )
            current = next_label
        composed = "vout"
        current_video = "[vout]"

    output_label = composed
    if show_labels and label_paths is not None and label_start is not None:
        windows = _label_time_windows(slides)
        current = current_video
        for index, (start, end) in enumerate(windows):
            label_index = label_start + index
            next_pad = f"vl{index}" if index < len(windows) - 1 else "vlabeled"
            filters.append(
                f"{current}[{label_index}:v]"
                f"overlay=40:40:format=auto:"
                f"enable='between(t\\,{start:.6f}\\,{end:.6f})'"
                f"[{next_pad}]"
            )
            current = f"[{next_pad}]"
        output_label = "vlabeled"

    if opts.audio is not None and audio_input_index is not None:
        filters.append(f"[{audio_input_index}:a]atrim=0:{total_duration:.6f},asetpts=PTS-STARTPTS[aout]")

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-stats",
        *input_args,
    ]
    if filters:
        command.extend(["-filter_complex", ";".join(filters)])
    command.extend(["-map", f"[{output_label}]"])
    if opts.audio is not None:
        command.extend(["-map", "[aout]"])
    command.extend([*_encode_args(opts), "-movflags", "+faststart"])
    if opts.audio is not None:
        command.extend(["-c:a", "aac", "-b:a", "192k"])
    command.append(str(output_path))
    return command


def build_ffmpeg_command(
    project: Project,
    output_path: Path,
    opts: RenderOptions,
    label_paths: list[Path] | None = None,
    clip_paths: list[Path] | None = None,
) -> list[str]:
    """
    Build the final compose command.

    When clip_paths is provided, those are pre-rendered slide clips.
    For --dry-run without clips, returns the compose command with placeholder
    slide inputs replaced by the source photos via a single-graph preview.
    """
    if clip_paths is None:
        # Dry-run helper: show a one-shot graph command for inspection.
        return _build_legacy_oneshot_command(project, output_path, opts, label_paths)
    return build_compose_command(project, clip_paths, output_path, opts, label_paths)


def _build_legacy_oneshot_command(
    project: Project,
    output_path: Path,
    opts: RenderOptions,
    label_paths: list[Path] | None,
) -> list[str]:
    """Single-graph command used only for --dry-run readability."""
    slides = project.slides
    total_duration = project.total_duration()
    show_labels = bool(label_paths) and opts.show_filenames

    input_args: list[str] = []
    for slide in slides:
        input_args.extend(
            [
                "-loop",
                "1",
                "-framerate",
                str(opts.fps),
                "-t",
                f"{slide.duration:.6f}",
                "-i",
                str(slide.file),
            ]
        )

    label_start: int | None = None
    if show_labels and label_paths is not None:
        label_start = len(slides)
        for path in label_paths:
            input_args.extend(
                [
                    "-loop",
                    "1",
                    "-framerate",
                    str(opts.fps),
                    "-t",
                    f"{total_duration:.6f}",
                    "-i",
                    str(path),
                ]
            )

    filters = [_slide_filter(slide, index, opts, f"v{index}") for index, slide in enumerate(slides)]
    if len(slides) == 1:
        composed = "v0"
    else:
        composed = "vout"
        offsets = _xfade_offsets(slides)
        current = "[v0]"
        for index in range(1, len(slides)):
            transition = slides[index - 1].transition
            next_label = f"[vx{index}]" if index < len(slides) - 1 else "[vout]"
            filters.append(
                f"{current}[v{index}]"
                f"xfade=transition={transition.type}:"
                f"duration={transition.duration:.6f}:"
                f"offset={offsets[index - 1]:.6f}"
                f"{next_label}"
            )
            current = next_label

    output_label = composed
    if show_labels and label_paths is not None and label_start is not None:
        windows = _label_time_windows(slides)
        current = f"[{composed}]"
        for index, (start, end) in enumerate(windows):
            label_index = label_start + index
            next_pad = f"vl{index}" if index < len(windows) - 1 else "vlabeled"
            filters.append(
                f"{current}[{label_index}:v]"
                f"overlay=40:40:format=auto:"
                f"enable='between(t\\,{start:.6f}\\,{end:.6f})'"
                f"[{next_pad}]"
            )
            current = f"[{next_pad}]"
        output_label = "vlabeled"

    command = [
        "ffmpeg",
        "-y",
        *input_args,
        "-filter_complex",
        ";".join(filters),
        "-map",
        f"[{output_label}]",
        *_encode_args(opts),
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    return command


def _make_labels(project: Project, directory: Path) -> list[Path]:
    paths: list[Path] = []
    for index, slide in enumerate(project.slides):
        path = directory / f"label_{index:03d}.png"
        render_label_png(slide.file.name, path)
        paths.append(path)
    return paths


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def render(project: Project, output_path: Path, opts: RenderOptions) -> list[str]:
    """
    Two-pass render for speed:
      1) encode each slide clip in parallel (camera only)
      2) xfade + labels (+ audio) into the final MP4
    """
    label_dir: Path | None = None
    label_paths: list[Path] | None = None
    work_dir: Path | None = None

    if opts.show_filenames:
        label_dir = Path(tempfile.mkdtemp(prefix="slideshow-labels-"))
        label_paths = _make_labels(project, label_dir)

    if opts.dry_run:
        command = build_ffmpeg_command(project, output_path, opts, label_paths)
        if label_dir is not None:
            shutil.rmtree(label_dir, ignore_errors=True)
        return command

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        if label_dir is not None:
            shutil.rmtree(label_dir, ignore_errors=True)
        raise RuntimeError("FFmpeg not found on PATH. Install FFmpeg before rendering (e.g. brew install ffmpeg).")

    work_dir = Path(tempfile.mkdtemp(prefix="slideshow-clips-"))
    try:
        clip_paths = [work_dir / f"slide_{index:03d}.mp4" for index in range(len(project.slides))]

        def _encode_one(index: int) -> None:
            slide = project.slides[index]
            command = build_slide_clip_command(slide, clip_paths[index], opts)
            command[0] = ffmpeg
            _run(command)

        workers = min(MAX_SLIDE_WORKERS, max(1, len(project.slides)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_encode_one, index) for index in range(len(project.slides))]
            for future in as_completed(futures):
                future.result()

        compose = build_compose_command(project, clip_paths, output_path, opts, label_paths)
        compose[0] = ffmpeg
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _run(compose)
        return compose
    finally:
        if work_dir is not None:
            shutil.rmtree(work_dir, ignore_errors=True)
        if label_dir is not None:
            shutil.rmtree(label_dir, ignore_errors=True)


def format_command(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)

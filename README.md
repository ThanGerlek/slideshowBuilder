# Slideshow Renderer

A declarative Python slideshow renderer that reads a JSON or YAML project file and generates a single FFmpeg filter graph to produce an MP4 video with Ken Burns camera motion and `xfade` transitions.

## Prerequisites

- **Python 3.10+**
- **PyYAML** (only required for `.yaml` / `.yml` configs; JSON works with the stdlib alone)
- **FFmpeg** installed and available on `PATH`

```bash
pip install -r requirements.txt

# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg
```

## Project layout

```text
slideshow/
├── slideshow.py      # Render CLI
├── update_config.py  # Sync config from photos/ only
├── models.py         # Dataclasses, config loading, defaults merge
├── config_io.py      # JSON / YAML load & save
├── validation.py     # Project validation
├── renderer.py       # FFmpeg filter graph builder
├── sync.py           # photos/ → config sync
├── config.yaml       # Sample project (also accepts .json / .yml)
├── generate_samples.py
├── photos/           # Slide images
└── output/           # Rendered videos
```

## Quick start

Generate sample images (if needed):

```bash
python3 slideshow/generate_samples.py
```

Sync `config.yaml` with `photos/` (no rendering):

```bash
python3 slideshow/update_config.py
# or: python3 slideshow/update_config.py slideshow/config.yaml
```

Preview the FFmpeg command without rendering:

```bash
python3 slideshow/slideshow.py slideshow/config.yaml --dry-run
```

Render the sample slideshow:

```bash
python3 slideshow/slideshow.py slideshow/config.yaml
```

`update_config.py` and the render CLI both sync the config with `photos/`: any new image files are added as slides (natural alphanumeric order), with a random `camera` and `transition.type`. Duration fields are omitted so defaults apply. Existing slide settings are preserved; slides whose files are gone from `photos/` are dropped. Sync rewrites the file in the same format (JSON or YAML).

Output defaults to `slideshow/output/slideshow.mp4`.

## CLI options

| Option           | Description                                          |
| ---------------- | ---------------------------------------------------- |
| `config`         | Path to JSON or YAML project file (required)         |
| `-o`, `--output` | Output MP4 path                                      |
| `--resolution`   | Output size as `WIDTHxHEIGHT` (default: `1920x1080`) |
| `--fps`          | Frame rate (default: `30`)                           |
| `--audio`        | Optional background audio file                       |
| `--dry-run`      | Print FFmpeg command without executing               |
| `--no-filenames` | Hide per-slide filename overlays (shown by default)  |
| `--preset`       | libx264 preset (default: `veryfast`)                 |
| `--crf`          | libx264 quality (default: `20`)                      |

## Project format (JSON or YAML)

Top-level structure (YAML shown; JSON uses the same keys):

```yaml
defaults:
  duration: 4.0
  transition:
    type: fade
    duration: 1.0
  camera: zoom-in
slides: []
```

Each slide requires `file`; all other fields inherit from `defaults`:

```yaml
- file: 001.jpg
  duration: 6.0
  transition:
    type: wipeleft
    duration: 0.75
  camera: kenburns # inline comments work in YAML
```

### Camera presets

`camera` is a preset name. Motion is resolved per image (cover-fit box, speed clamping, smoothstep easing).

| Preset                   | Motion                       |
| ------------------------ | ---------------------------- |
| `static`                 | Steady hold with slight zoom |
| `zoom-in`                | Center, zoom in              |
| `zoom-out`               | Center, zoom out             |
| `pan-left` / `pan-right` | Horizontal Ken Burns         |
| `pan-up` / `pan-down`    | Vertical Ken Burns           |
| `kenburns`               | Diagonal drift + zoom in     |
| `kenburns-reverse`       | Diagonal drift + zoom out    |

### Transitions

Transition `type` maps directly to FFmpeg `xfade` transition names (e.g. `fade`, `wipeleft`, `wiperight`, `slideleft`, `dissolve`, …).

## Rendering pipeline

1. Load and parse JSON or YAML
2. Merge per-slide defaults
3. Validate files, ranges, and transition types
4. Build per-slide `scale` + `crop` filters for Ken Burns motion
5. Chain slides with `xfade` at computed offsets
6. Optionally mix background audio
7. Encode H.264/AAC MP4

## Design goals

- Declarative JSON/YAML project format
- Renderer independent of config parsing
- Easy to extend with new camera presets, transitions, and validation rules
- All visual rendering delegated to FFmpeg

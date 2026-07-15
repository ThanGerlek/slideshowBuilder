# Slideshow Project Ideation

## Overview
A Python application renders slideshow videos by reading a JSON project file and generating a single FFmpeg filter graph.

Responsibilities:
- Python: parse, validate, compute timing, generate FFmpeg graph.
- FFmpeg: image scaling, camera motion, transitions, encoding.

## Project Layout

```text
slideshow/
├── slideshow.py
├── models.py
├── renderer.py
├── config.json
├── photos/
└── output/
JSON Schema

Top level:

{
  "defaults": {
    "duration": 4.0,
    "transition": {
      "type": "fade",
      "duration": 1.0
    },
    "camera": {
      "start": "center",
      "end": "center",
      "zoom_start": 1.0,
      "zoom_end": 1.15,
      "easing": "linear"
    }
  },
  "slides": []
}

Each slide:

{
  "file": "001.jpg",
  "duration": 6.0,
  "transition": {
    "type": "wipeleft",
    "duration": 0.75
  },
  "camera": {
    "start": "top-left",
    "end": "bottom-right",
    "zoom_start": 1.0,
    "zoom_end": 1.25,
    "easing": "ease_in_out"
  }
}

All slide fields are optional except file. Missing values inherit from defaults.

Camera

Named anchors:

center
top, bottom, left, right
top-left, top-right
bottom-left, bottom-right

Future versions may also accept normalized coordinates:

{ "start":[0.1,0.2], "end":[0.8,0.7] }

Fields:

start
end
zoom_start
zoom_end
easing
Transition

Fields:

type
duration

Transition type maps directly to FFmpeg xfade.

Python Model
@dataclass
class Camera:
    start: str | tuple[float,float]
    end: str | tuple[float,float]
    zoom_start: float
    zoom_end: float
    easing: str = "linear"

@dataclass
class Transition:
    type: str
    duration: float

@dataclass
class Slide:
    file: Path
    duration: float
    camera: Camera
    transition: Transition

@dataclass
class Project:
    slides: list[Slide]
Rendering Pipeline
Load JSON.
Merge defaults into each slide.
Validate references and values.
Create one FFmpeg filter chain per slide.
Apply scaling/padding.
Apply camera motion (zoompan or equivalent).
Connect slides with xfade.
Optionally add background music.
Encode final MP4.
Design Goals
Declarative JSON project.
Renderer independent of JSON parsing.
Easy to add camera presets, transitions, and validation.
Keep all rendering inside FFmpeg.

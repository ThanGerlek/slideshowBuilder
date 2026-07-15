"""Project validation with aggregated error reporting."""

from __future__ import annotations

from models import CAMERA_PRESETS, Project, XFADE_TRANSITIONS


class ValidationError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        message = "Project validation failed:\n" + "\n".join(f"  - {err}" for err in errors)
        super().__init__(message)


def validate_project(project: Project) -> None:
    errors: list[str] = []

    if not project.slides:
        errors.append("Project must include at least one slide.")
        raise ValidationError(errors)

    preset_names = ", ".join(sorted(CAMERA_PRESETS))

    for index, slide in enumerate(project.slides):
        prefix = f"Slide {index} ({slide.file.name})"

        if not slide.file.exists():
            errors.append(f"{prefix}: image file not found at {slide.file}")

        if slide.duration <= 0:
            errors.append(f"{prefix}: duration must be greater than 0")

        if slide.transition.duration < 0:
            errors.append(f"{prefix}: transition duration must be >= 0")

        if slide.transition.type not in XFADE_TRANSITIONS:
            errors.append(f"{prefix}: transition type {slide.transition.type!r} is not supported")

        if index < len(project.slides) - 1:
            if slide.transition.duration >= slide.duration:
                errors.append(f"{prefix}: transition duration must be less than slide duration")

        if slide.camera not in CAMERA_PRESETS:
            errors.append(
                f"{prefix}: camera preset {slide.camera!r} is not recognized (expected one of: {preset_names})"
            )

    if errors:
        raise ValidationError(errors)

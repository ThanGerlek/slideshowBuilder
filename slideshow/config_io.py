"""Load and save slideshow project configs as JSON or YAML."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

JSON_SUFFIXES = frozenset({".json"})
YAML_SUFFIXES = frozenset({".yaml", ".yml"})
SUPPORTED_SUFFIXES = JSON_SUFFIXES | YAML_SUFFIXES


def config_format(path: Path) -> str:
    """Return 'json' or 'yaml' based on file suffix."""
    suffix = path.suffix.lower()
    if suffix in JSON_SUFFIXES:
        return "json"
    if suffix in YAML_SUFFIXES:
        return "yaml"
    raise ValueError(
        f"Unsupported config format {path.suffix!r}; expected one of: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
    )


def _load_yaml(text: str) -> Any:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("YAML configs require PyYAML. Install with: pip install PyYAML") from exc
    return yaml.safe_load(text)


def _dump_yaml(data: dict[str, Any]) -> str:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("YAML configs require PyYAML. Install with: pip install PyYAML") from exc
    return yaml.safe_dump(
        data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )


def load_config_dict(path: Path) -> dict[str, Any]:
    """Read a project config file into a dict (.json / .yaml / .yml)."""
    path = path.resolve()
    fmt = config_format(path)
    text = path.read_text(encoding="utf-8")
    if fmt == "json":
        data = json.loads(text)
    else:
        data = _load_yaml(text)

    if not isinstance(data, dict):
        raise ValueError("Project config must be a mapping/object at the top level.")
    return data


def save_config_dict(path: Path, data: dict[str, Any]) -> None:
    """Write a project config dict, preserving the path's format."""
    path = path.resolve()
    fmt = config_format(path)
    if fmt == "json":
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return
    path.write_text(_dump_yaml(data), encoding="utf-8")

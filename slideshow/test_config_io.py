"""Tests for JSON/YAML config I/O."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from config_io import load_config_dict, save_config_dict
from models import load_project


SAMPLE = {
    "defaults": {
        "duration": 4.0,
        "transition": {"type": "fade", "duration": 1.0},
        "camera": "static",
    },
    "slides": [
        {"file": "a.jpg", "camera": "zoom-in", "transition": {"type": "fade"}},
    ],
}


class ConfigIoTests(unittest.TestCase):
    def test_roundtrip_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            save_config_dict(path, SAMPLE)
            loaded = load_config_dict(path)
            self.assertEqual(loaded["defaults"]["camera"], "static")
            self.assertEqual(loaded["slides"][0]["file"], "a.jpg")

    def test_roundtrip_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            save_config_dict(path, SAMPLE)
            text = path.read_text(encoding="utf-8")
            self.assertIn("camera: static", text)
            loaded = load_config_dict(path)
            self.assertEqual(loaded["slides"][0]["camera"], "zoom-in")

    def test_yaml_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yml"
            path.write_text(
                "defaults:\n  camera: static\nslides:\n  - file: a.jpg\n    camera: zoom-in  # note\n",
                encoding="utf-8",
            )
            loaded = load_config_dict(path)
            self.assertEqual(loaded["slides"][0]["camera"], "zoom-in")

    def test_unsupported_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text("x = 1\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config_dict(path)


class LoadProjectYamlTests(unittest.TestCase):
    def test_load_yaml_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "photos").mkdir()
            # Empty photo file so path exists for validation later if needed
            (root / "photos" / "a.jpg").write_bytes(b"")
            path = root / "config.yaml"
            save_config_dict(path, SAMPLE)
            project = load_project(path)
            self.assertEqual(len(project.slides), 1)
            self.assertEqual(project.slides[0].camera, "zoom-in")
            self.assertEqual(project.slides[0].file.name, "a.jpg")


if __name__ == "__main__":
    unittest.main()

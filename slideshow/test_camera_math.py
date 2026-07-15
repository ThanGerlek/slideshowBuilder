"""Unit tests for pan/zoom geometry (pan-and-zoom-math.md)."""

from __future__ import annotations

import math
import unittest

from camera_math import (
    DEFAULT_V_TARGET,
    Corner,
    KenBurnsMode,
    PanDirection,
    PresetIntent,
    box_max_distance,
    cover_scale,
    ease_smoothstep,
    feasible_box,
    margins,
    pan_zoom_distance,
    resolve_preset,
    window_size,
)


class WorkedExampleTests(unittest.TestCase):
    """§12: 4000×2000 panorama into 1600×900 viewport."""

    W, H = 4000, 2000
    VW, VH = 1600, 900

    def test_cover_scale(self) -> None:
        s = cover_scale(self.W, self.H, self.VW, self.VH)
        self.assertAlmostEqual(s, 0.45)

    def test_window_at_z1(self) -> None:
        s = cover_scale(self.W, self.H, self.VW, self.VH)
        w, h = window_size(1.0, s, self.VW, self.VH)
        self.assertAlmostEqual(w, 1600 / 0.45)
        self.assertAlmostEqual(h, 2000.0)

    def test_margins_at_z1_degenerate_vertical(self) -> None:
        mx, my = margins(1.0, self.W, self.H, self.VW, self.VH)
        self.assertAlmostEqual(mx, 3556 / 8000, places=3)
        self.assertAlmostEqual(my, 0.5)

    def test_box_at_z1_1(self) -> None:
        # Doc: mx(1.1)=0.404, my≈0.4545; u ∈ [0.404, 0.596]
        box = feasible_box(1.1, self.W, self.H, self.VW, self.VH)
        self.assertAlmostEqual(box.u_min, 0.404, places=3)
        self.assertAlmostEqual(box.u_max, 1.0 - 0.404, places=3)
        self.assertAlmostEqual(box.v_min, 0.4545, places=3)
        self.assertAlmostEqual(box.v_max, 1.0 - 0.4545, places=3)

    def test_max_distance_horizontal_room(self) -> None:
        # §8: full box diagonal in screen px (doc's ≈380 ignored vertical slack).
        mx, my = margins(1.1, self.W, self.H, self.VW, self.VH)
        box_w = (1.0 - 2.0 * mx) * self.W
        box_h = (1.0 - 2.0 * my) * self.H
        expected = 0.45 * 1.1 * math.hypot(box_w, box_h)
        d = box_max_distance(1.1, self.W, self.H, self.VW, self.VH)
        self.assertAlmostEqual(d, expected, places=6)
        # Horizontal component alone is the doc's ~380 figure.
        self.assertAlmostEqual(0.495 * box_w, 380.0, delta=2.0)


class BoxNestingTests(unittest.TestCase):
    def test_box_grows_with_zoom(self) -> None:
        w, h, vw, vh = 4000, 2000, 1600, 900
        box_lo = feasible_box(1.05, w, h, vw, vh)
        box_hi = feasible_box(1.2, w, h, vw, vh)
        self.assertLessEqual(box_hi.u_min, box_lo.u_min)
        self.assertGreaterEqual(box_hi.u_max, box_lo.u_max)
        self.assertLessEqual(box_hi.v_min, box_lo.v_min)
        self.assertGreaterEqual(box_hi.v_max, box_lo.v_max)

    def test_near_square_collapses_at_z1(self) -> None:
        # Image aspect ≈ viewport → Box(1) is a point.
        box = feasible_box(1.0, 1600, 900, 1600, 900)
        self.assertAlmostEqual(box.u_min, 0.5)
        self.assertAlmostEqual(box.u_max, 0.5)
        self.assertAlmostEqual(box.v_min, 0.5)
        self.assertAlmostEqual(box.v_max, 0.5)


class EasingTests(unittest.TestCase):
    def test_smoothstep_endpoints(self) -> None:
        self.assertEqual(ease_smoothstep(0.0), 0.0)
        self.assertEqual(ease_smoothstep(1.0), 1.0)

    def test_smoothstep_mid(self) -> None:
        self.assertAlmostEqual(ease_smoothstep(0.5), 0.5)


class ResolvePresetTests(unittest.TestCase):
    W, H = 4000, 2000
    VW, VH = 1600, 900

    def _assert_in_box(self, cam, z_min: float) -> None:
        box = feasible_box(z_min, self.W, self.H, self.VW, self.VH)
        for u, v in ((cam.u_start, cam.v_start), (cam.u_end, cam.v_end)):
            self.assertGreaterEqual(u, box.u_min - 1e-9)
            self.assertLessEqual(u, box.u_max + 1e-9)
            self.assertGreaterEqual(v, box.v_min - 1e-9)
            self.assertLessEqual(v, box.v_max + 1e-9)

    def test_pan_right_clamps_to_speed_budget(self) -> None:
        # Desired = 40*4 = 160; max horizontal room ≈ 380 → use 160, not full span.
        intent = PresetIntent(z_start=1.1, z_end=1.1, pan=PanDirection.RIGHT)
        cam = resolve_preset(intent, self.W, self.H, self.VW, self.VH, duration=4.0, v_target=40.0)
        self.assertAlmostEqual(cam.zoom_start, 1.1)
        self.assertAlmostEqual(cam.zoom_end, 1.1)
        self.assertAlmostEqual(cam.v_start, 0.5)
        self.assertAlmostEqual(cam.v_end, 0.5)
        self.assertLess(cam.u_start, cam.u_end)
        dist = pan_zoom_distance(
            cam.u_start,
            cam.v_start,
            cam.u_end,
            cam.v_end,
            cam.zoom_start,
            cam.zoom_end,
            self.W,
            self.H,
            self.VW,
            self.VH,
        )
        self.assertAlmostEqual(dist, 160.0, delta=1.0)
        self._assert_in_box(cam, 1.1)

    def test_pan_uses_all_room_when_budget_large(self) -> None:
        intent = PresetIntent(z_start=1.1, z_end=1.1, pan=PanDirection.RIGHT)
        cam = resolve_preset(intent, self.W, self.H, self.VW, self.VH, duration=4.0, v_target=500.0)
        box = feasible_box(1.1, self.W, self.H, self.VW, self.VH)
        self.assertAlmostEqual(cam.u_start, box.u_min, places=5)
        self.assertAlmostEqual(cam.u_end, box.u_max, places=5)

    def test_static_center(self) -> None:
        intent = PresetIntent(z_start=1.06, z_end=1.06)
        cam = resolve_preset(intent, self.W, self.H, self.VW, self.VH, duration=4.0)
        self.assertEqual((cam.u_start, cam.v_start, cam.u_end, cam.v_end), (0.5, 0.5, 0.5, 0.5))

    def test_zoom_in_respects_budget(self) -> None:
        intent = PresetIntent(z_start=1.05, z_end=1.15)
        cam = resolve_preset(intent, self.W, self.H, self.VW, self.VH, duration=4.0, v_target=40.0)
        dist = pan_zoom_distance(
            cam.u_start,
            cam.v_start,
            cam.u_end,
            cam.v_end,
            cam.zoom_start,
            cam.zoom_end,
            self.W,
            self.H,
            self.VW,
            self.VH,
        )
        self.assertLessEqual(dist, 40.0 * 4.0 + 1.0)
        self.assertEqual(cam.u_start, 0.5)
        self.assertGreaterEqual(cam.zoom_end, cam.zoom_start)

    def test_kenburns_endpoints_in_box(self) -> None:
        intent = PresetIntent(
            z_start=1.05,
            z_end=1.15,
            kenburns=KenBurnsMode.CORNER_TO_CENTER,
            corner=Corner.BR,
        )
        cam = resolve_preset(intent, self.W, self.H, self.VW, self.VH, duration=4.0)
        self._assert_in_box(cam, min(cam.zoom_start, cam.zoom_end))
        self.assertGreater(cam.u_start, cam.u_end)  # from BR toward center
        self.assertGreater(cam.v_start, cam.v_end)

    def test_near_square_pan_degrades_to_static_like(self) -> None:
        # At z slightly above 1 on a matching aspect, tiny box → tiny or zero travel.
        intent = PresetIntent(z_start=1.05, z_end=1.05, pan=PanDirection.RIGHT)
        cam = resolve_preset(intent, 1600, 900, 1600, 900, duration=4.0, v_target=DEFAULT_V_TARGET)
        box = feasible_box(1.05, 1600, 900, 1600, 900)
        self.assertGreaterEqual(cam.u_start, box.u_min - 1e-9)
        self.assertLessEqual(cam.u_end, box.u_max + 1e-9)
        # Travel cannot exceed the tiny box width.
        self.assertLessEqual(abs(cam.u_end - cam.u_start), box.width + 1e-9)


if __name__ == "__main__":
    unittest.main()

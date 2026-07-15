# The Mathematics of Pan-and-Zoom (Ken Burns) Presets

## 1. Setup and notation

Each image has pixel dimensions `W × H`. The viewport (the screen region the
slide renders into) has dimensions `Vw × Vh`. Both can be any aspect ratio,
and they usually don't match.

The animation is defined by a moving **crop window**: an axis-aligned
rectangle in image-pixel space that gets scaled up to fill the viewport each
frame. Animating the window's size (zoom) and position (pan) is the entire
effect — there is no other moving part.

```
image space (W × H)              viewport (Vw × Vh)
┌────────────────────┐
│                     │           ┌───────────┐
│   ┌─────────┐       │   render  │           │
│   │  crop   │───────┼──────────▶│  crop      │
│   │ window  │       │  scale up │  window    │
│   └─────────┘       │           │           │
│                     │           └───────────┘
└────────────────────┘
```

## 2. The cover-fit scale

For the crop window to fill the viewport with **no letterboxing at any
point in the animation**, we anchor everything to the same reference used by
CSS `background-size: cover`:

```
s_cover = max( Vw / W , Vh / H )
```

This is the *smallest* scale factor that still covers the viewport
completely. At this scale, one dimension of the image maps exactly onto the
viewport and the other overflows it. That overflowing dimension is the only
one with room to crop/pan.

## 3. Zoom as an inverse window size

Define zoom level `z ≥ 1`. At `z = 1` the crop window is the *largest*
window with the viewport's aspect ratio that still fits inside the image —
i.e., it shows the maximum possible content while satisfying "fill, don't
letterbox." Increasing `z` shrinks the window (classic "zoom in").

```
w(z) = Vw / (s_cover · z)      ← crop window width, in image pixels
h(z) = Vh / (s_cover · z)      ← crop window height, in image pixels
```

Check at `z = 1`: if `Vw/W ≥ Vh/H` (viewport is relatively wider than the
image), then `s_cover = Vw/W`, giving `w(1) = W` (full width shown) and
`h(1) = Vh·W/Vw ≤ H` (height is the cropped dimension). This is exactly
"show most of the image" — at minimum zoom you only ever crop the one
dimension that has to give, never both.

`z_screen-scale`, the actual CSS/canvas scale factor applied to the image, is:

```
s(z) = s_cover · z
```

## 4. The pan-range lemma (why this matters)

Let the crop window be centered at `(cx, cy)` in image pixels. For the
window to stay inside the image:

```
cx ∈ [ w(z)/2 , W − w(z)/2 ]
cy ∈ [ h(z)/2 , H − h(z)/2 ]
```

Normalize to `u = cx/W, v = cy/H ∈ [0,1]` and define the **margin**:

```
mx(z) = w(z) / (2W)
my(z) = h(z) / (2H)
```

so the feasible center region is the box:

```
Box(z) = [ mx(z), 1−mx(z) ] × [ my(z), 1−my(z) ]
```

**Lemma (nesting):** since `w(z)` and `h(z)` are strictly decreasing in `z`,
`mx(z)` and `my(z)` are too — so for `z₂ > z₁`, `Box(z₂) ⊇ Box(z₁)`. The
feasible pan region only grows as you zoom in, and it's *smallest* at the
animation's minimum zoom.

**Consequence:** if you compute two center points `u_start, u_end` that are
both valid inside `Box(z_min)` where `z_min = min(z(t))` over the whole
animation, then *linear interpolation between them stays valid for every
frame*, regardless of the zoom easing curve, because every intermediate
`Box(z(t))` is a superset of `Box(z_min)`. This is the key simplification:
compute your pan bounds once, at the tightest zoom, and never worry about
per-frame clipping.

One immediate edge case falls out of this: at `z = 1` in the limiting
dimension, `mx = 0.5` exactly, so `Box(1)` is a degenerate line segment in
that axis — **zero pan room**. Any preset that pans in that axis needs
`z_min > 1` by at least a small margin.

## 5. Trajectories and easing

A preset is a pair of functions over normalized time `τ ∈ [0,1]`:

```
z(τ) = z_start + (z_end − z_start) · e(τ)
u(τ) = u_start + (u_end − u_start) · e(τ)
v(τ) = v_start + (v_end − v_start) · e(τ)
```

using a single shared easing function `e(τ)` (so zoom and pan stay in sync
and finish together). A good default is smoothstep / ease-in-out cubic:

```
e(τ) = 3τ² − 2τ³          (or, more filmic: e(τ) = τ² (3 − 2τ) again — 
                            same thing; use quintic 6τ⁵−15τ⁴+10τ³ for a 
                            gentler start/stop)
```

Constant-velocity linear motion (`e(τ) = τ`) reads as mechanical; ease-in-out
is what makes it look "cinematic" rather than "slideshow software."

Real time: `t = τ · T` for total slide duration `T` seconds.

## 6. A unified distance metric (pan + zoom together)

To control "speed," you need one scalar that combines *panning* (measured
in screen pixels) and *zooming* (measured as a scale ratio, unitless) into
one comparable travel distance. Two different physical units don't have an
obvious sum, so pick a reference length — the viewport diagonal — and
convert zoom into "equivalent pixels moved":

```
diag = √(Vw² + Vh²)

pan_distance   = s(z_avg) · √( (cx_end − cx_start)² + (cy_end − cy_start)² )
                  ↳ Euclidean travel of the crop-window center, in *screen* pixels
                  ↳ z_avg = (z_start + z_end)/2 is a good-enough approximation
                    of the scale in effect while panning

zoom_distance  = k · diag · |ln(z_end / z_start)|
                  ↳ k ≈ 1 is a tunable "how much perceived motion does a 
                    zoom-doubling equal" constant; k=1 means doubling zoom 
                    reads as about one full diagonal-length of travel

total_distance = √( pan_distance² + zoom_distance² )
```

This lets every preset — pure pan, pure zoom, or combined — be described by
a single `total_distance` in a common unit (screen pixels), which is what
makes cross-image speed comparison possible.

## 7. Normalizing speed across images

This is the part that differs image to image, because `Box(z_min)` — the
available pan room — depends entirely on how close the image's aspect ratio
is to the viewport's. A panoramic image has enormous horizontal slack; a
near-square image cropped into a widescreen viewport has almost none.

Pick **one** of these as your free variable:

**(A) Fixed duration, speed floats (simplest, most common in slideshow software)**
```
T = constant (e.g. 6s per slide)
speed = total_distance / T
```
Different images move at different perceived speeds. Fine for casual use,
but a panoramic photo will visibly "fly by" faster than a boxy one if you
push both to the same zoom delta.

**(B) Fixed target speed, duration floats**
```
v_target = constant (e.g. 40 px/sec of viewport-scale motion)
T = total_distance / v_target
```
Every image moves at the same perceived rate; slide duration varies. Better
perceptual consistency, worse for a slideshow with a fixed music/beat timing.

**(C) Fixed duration AND fixed speed — solve for travel distance (recommended)**
This is the one that actually answers "adjust the speed via travel
distance": treat `T` and `v_target` as both fixed, and instead scale *how
far* the preset travels to make the two consistent, capped by what
`Box(z_min)` can actually provide:

```
desired_distance = v_target · T
max_distance      = distance between the two farthest-apart valid points 
                     in Box(z_min) at the preset's zoom range (see §8)
actual_distance   = min(desired_distance, max_distance)
```

Then re-derive the endpoint `(u_end, v_end)` and `z_end` by scaling the
preset's *direction vector* to `actual_distance` instead of using a fixed
offset. A panoramic image (large `max_distance`) gets the full desired pan;
a boxy image (small `max_distance`) automatically gets a shorter, gentler
pan rather than being forced out of bounds or made to move too fast to
cover extra distance in the same time. This is what keeps "most of the
image visible at all times" true simultaneously with "consistent speed."

Concretely, for a preset whose direction in normalized-center space is unit
vector `d̂ = (du, dv)` from a chosen start point, solve for the largest `r`
such that `start + r·d̂ ∈ Box(z_min)`, then set:

```
r_used = min( r_max_from_box , actual_distance / |pan_distance_per_unit_r| )
```

i.e. clamp whichever binds first — the geometry of the box, or the
speed/duration budget.

## 8. Computing max_distance (the box diagonal)

For a given `z_min`, the farthest apart two valid centers can be (i.e. the
biggest possible pan) is the box's own diagonal:

```
box_w = (1 − 2·mx(z_min)) · W        ← in image pixels
box_h = (1 − 2·my(z_min)) · H

max_distance = s(z_min) · √(box_w² + box_h²)     ← in screen pixels
```

If `box_w` or `box_h` is ≤ 0, that axis has no pan room at `z_min` — increase
`z_min` slightly (i.e. never let the min zoom touch exactly 1 for presets
that pan along the limiting dimension).

## 9. Standard presets, parametrized

Let `zN` be a "near" zoom (e.g. `1.15`) and `zF` a "far"/base zoom
(`1.0` or slightly above, per §8). `(u_c, v_c) = (0.5, 0.5)` is center.

| Preset | z_start → z_end | u,v path (start → end) | Notes |
|---|---|---|---|
| **Zoom in, static center** | `zF → zN` | `(0.5,0.5) → (0.5,0.5)` | z_min = zF, use §7/§8 to size zN if you want zoom amount speed-normalized too (via zoom_distance) |
| **Zoom out, static center** | `zN → zF` | `(0.5,0.5) → (0.5,0.5)` | reverse of above |
| **Pan L→R** | `zN → zN` (const) | `(mx(zN), 0.5) → (1−mx(zN), 0.5)` | requires zN > 1 in the width axis per the degenerate case in §4 |
| **Pan T→B** | `zN → zN` (const) | `(0.5, my(zN)) → (0.5, 1−my(zN))` | symmetric case |
| **Diagonal drift + zoom in** | `zF → zN` | `Box(zF)` corner → center | most "documentary" feeling; compute corner as `(mx(zF), my(zF))` etc. |
| **Diagonal drift + zoom out** | `zN → zF` | center → `Box(zF)` corner | reverse |

For the "pan across a wide box" presets, endpoints should be derived via §7
(actual_distance) rather than hard-coded fractions, so a very elongated
image gets a proportionally longer, and a near-square image a shorter, pan
— all inside the same `T`.

## 10. Edge cases

- **Aspect ratio ≈ viewport aspect ratio**: `Box(1)` collapses in *both*
  axes simultaneously (it's a point). All presets must use `z_min > 1`
  here, or fall back to a zoom-only preset — panning is geometrically
  meaningless when there's no slack.
- **Extreme panorama** (`W/H ≫ Vw/Vh`): `max_distance` in the horizontal
  axis becomes huge. Cap `actual_distance` via `desired_distance` (§7C) so
  the pan doesn't feel unnaturally fast — this is exactly the case the
  fixed-speed clamp is for.
- **Image smaller than viewport** (upscaling): `s_cover > 1` is still valid
  math, but note you're upscaling a raster image — consider capping
  `z_end` so `s(z_end) · original_resolution` doesn't exceed a quality
  threshold (e.g. 2× native pixels).
- **Portrait image in landscape viewport (or vice versa)**: this is the
  normal case the whole framework targets, not really an edge case — `s_cover`
  and `Box(z)` already account for it. Just make sure `z_min` clears the
  degenerate-axis threshold in whichever axis is limiting.

## 11. Algorithm summary

```
for each image (W,H) and viewport (Vw,Vh):
    s_cover = max(Vw/W, Vh/H)
    choose preset → get z_start, z_end, direction d̂ in (u,v) space
    z_min = min(z_start, z_end)
    compute Box(z_min) → mx, my
    compute max_distance = box diagonal in screen px at z_min  (§8)
    desired_distance = v_target * T
    actual_distance = min(desired_distance, max_distance)
    solve r: start + r*d̂ stays inside Box(z_min), scaled to actual_distance
    set final (u_start,v_start), (u_end,v_end)
    for each frame at time t:
        τ = t / T
        e = ease(τ)
        z = lerp(z_start, z_end, e)
        u = lerp(u_start, u_end, e)
        v = lerp(v_start, v_end, e)
        crop_w = Vw / (s_cover * z);  crop_h = Vh / (s_cover * z)
        crop_x = u*W - crop_w/2;      crop_y = v*H - crop_h/2
        render image cropped to (crop_x, crop_y, crop_w, crop_h), 
               scaled to (Vw, Vh)
```

## 12. Worked example

Image: `4000×2000` (2:1 panorama). Viewport: `1600×900` (16:9 ≈ 1.78:1).

```
s_cover = max(1600/4000, 900/2000) = max(0.4, 0.45) = 0.45
w(1) = 1600/0.45 = 3556 px      h(1) = 900/0.45 = 2000 px  (= H, as expected: 
                                                              height is the limiting dim)
```

So at `z=1`, the crop shows the full height and 3556 of 4000px width — the
image already has slack of `4000 − 3556 = 444px` horizontally even before
zooming in. `mx(1) = 3556/(2·4000) = 0.4445`, `my(1) = 0.5` (degenerate, as
predicted — the limiting dimension has zero vertical room at z=1).

Pick "Pan L→R" preset at `z = 1.1`:
```
w(1.1) = 3556/1.1 = 3233px → mx(1.1) = 3233/8000 = 0.404
h(1.1) = 2000/1.1 = 1818px → my(1.1) = 1818/4000 = 0.4545  (now non-degenerate)
```
Box(1.1) horizontal range: `u ∈ [0.404, 0.596]`, giving `box_w = (1−0.808)·4000 = 768px`
of image-space room, i.e. `max_distance = s(1.1)·768 = 0.495·768 ≈ 380` screen px
of pure horizontal travel available. If `v_target·T` (§7) asks for more than
380px of motion, it gets clamped to 380px automatically — the pan simply
uses all the room the image has, at the target speed, for as much of `T` as
that takes, rather than overshooting the frame.

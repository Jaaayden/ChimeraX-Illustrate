"""Pure-Python implementation of the Illustrate raster rendering pipeline.

The original project uses a fixed-size Fortran frame buffer and PPM output.  This
module keeps the same units and the same order of operations, while representing
the input as immutable Python data so it can be rendered outside ChimeraX's UI
thread. NumPy is optional for the core implementation and supplies the
accelerated backend when available; the public data model is unchanged.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from functools import lru_cache
import math
import os
import struct
from threading import Lock
from typing import Iterable, List, Optional, Sequence, Tuple
import zlib

try:
    import numpy as _np
except ImportError:  # The renderer remains testable without ChimeraX/NumPy.
    _np = None


_SHADOW_WORKERS = min(4, os.cpu_count() or 1)
_SHADOW_EXECUTOR = ThreadPoolExecutor(
    max_workers=_SHADOW_WORKERS, thread_name_prefix="illustrate-shadow"
)
_RASTER_CACHE_LOCK = Lock()
_RASTER_CACHE = {
    "scene": None,
    "key": None,
    "depth": None,
    "atom_map": None,
    "origin": None,
}
_SHADOW_CACHE_LOCK = Lock()
_SHADOW_CACHE = {
    "owner": None,
    "key": None,
    "shadow": None,
}
_PNG_COMPRESSION_LEVEL = 3
_PNG_IDAT_CHUNK_SIZE = 1024 * 1024


Color = Tuple[float, float, float]
Vec3 = Tuple[float, float, float]
Matrix3 = Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]


IDENTITY: Matrix3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


@dataclass(frozen=True)
class AtomRecord:
    """The scene information needed by Illustrate's atom renderer."""

    coord: Vec3
    color: Color
    radius: float
    subunit: str
    residue: int
    atom_name: str = ""


@dataclass(frozen=True)
class RenderScene:
    atoms: Tuple[AtomRecord, ...]


@dataclass(frozen=True)
class ViewSnapshot:
    """Camera transform in Illustrate screen coordinates.

    The rows of ``rotation`` map scene coordinates to x-screen, y-screen and z
    coordinates.  The y row is expected to increase downwards, matching the
    original renderer's image coordinate system.
    """

    rotation: Matrix3 = IDENTITY
    translation: Vec3 = (0.0, 0.0, 0.0)
    pixels_per_angstrom: float = 12.0
    auto_center: bool = True
    projection: str = "orthographic"


@dataclass(frozen=True)
class IllustrationStyle:
    """Illustrate parameters, retaining the original units and defaults."""

    background: Color = (1.0, 1.0, 1.0)
    fog_color: Color = (1.0, 1.0, 1.0)
    fog_front: float = 1.0
    fog_back: float = 1.0
    shadows: bool = True
    shadow_contribution: float = 0.0023
    shadow_cone_angle: float = 2.0
    shadow_depth: float = 1.0
    # Match the reference Illustrate input: shadows are allowed to darken
    # pixels down to 70% brightness, rather than the much darker 20% floor.
    shadow_maximum: float = 0.7
    contour_low: float = 3.0
    contour_high: float = 10.0
    # The reference front illustration uses the broadest, smoothest kernel.
    contour_kernel: int = 4
    contour_depth_min: float = 0.0
    contour_depth_max: float = 5.0
    subunit_low: float = 3.0
    subunit_high: float = 10.0
    residue_low: float = 3.0
    residue_high: float = 8.0
    # Small residue-number changes are part of the reference illustration's
    # internal boundaries; 6000 would suppress them almost completely.
    residue_difference: float = 6.0
    radius_scale: float = 1.0
    # Internal pixel-neighborhood scale used when an export is larger than
    # the canonical 1200 px reference render.  It is not a user parameter.
    raster_scale: float = 1.0


def scale_style_for_output(style: IllustrationStyle, output_width: int,
                            capture_width: int) -> IllustrationStyle:
    """Scale pixel-based thresholds for a resized render.

    The camera scale and the depth buffer are measured in pixels.  Keeping
    these thresholds and their pixel neighborhoods proportional to the output
    width prevents a different export size from changing the contour and
    shadow sensitivity.
    """

    scale = float(output_width) / float(max(1, capture_width))
    # Kernels 1/2 return a depth-derivative in pixel units.  Kernels 3/4
    # return a count-like sum of normalized neighbor differences, so their
    # contour low/high controls must remain dimensionless across output sizes.
    threshold_scale = scale if style.contour_kernel in (1, 2) else 1.0
    return replace(
        style,
        contour_low=style.contour_low * threshold_scale,
        contour_high=style.contour_high * threshold_scale,
        contour_depth_min=style.contour_depth_min * scale,
        contour_depth_max=style.contour_depth_max * scale,
        shadow_depth=style.shadow_depth * scale,
        raster_scale=max(1.0, float(output_width) / 1200.0),
    )


@dataclass(frozen=True)
class RenderedImage:
    width: int
    height: int
    rgba: bytes
    background: Color

    def composited_rgba(self, transparent: bool = True) -> bytes:
        if transparent:
            return self.rgba
        br, bg, bb = (max(0, min(255, int(round(c * 255.0)))) for c in self.background)
        if _np is not None:
            source = _np.frombuffer(self.rgba, dtype=_np.uint8).reshape(
                self.height, self.width, 4
            )
            output = bytearray(len(self.rgba))
            target = _np.frombuffer(output, dtype=_np.uint8).reshape(
                self.height, self.width, 4
            )
            background = _np.asarray((br, bg, bb), dtype=_np.uint16)
            # Work in row tiles so an opaque 8K export does not need several
            # additional full-resolution uint16 compositing buffers.
            for y0 in range(0, self.height, 512):
                y1 = min(self.height, y0 + 512)
                tile = source[y0:y1]
                alpha = tile[..., 3].astype(_np.uint16)
                inverse = 255 - alpha
                target[y0:y1, :, :3] = (
                    (
                        tile[..., :3].astype(_np.uint16) * alpha[..., None]
                        + background * inverse[..., None]
                    )
                    // 255
                ).astype(_np.uint8)
                target[y0:y1, :, 3] = 255
            return bytes(output)
        out = bytearray(len(self.rgba))
        for i in range(0, len(self.rgba), 4):
            alpha = self.rgba[i + 3]
            if alpha == 255:
                out[i:i + 4] = self.rgba[i:i + 4]
            elif alpha == 0:
                out[i:i + 4] = bytes((br, bg, bb, 255))
            else:
                inv = 255 - alpha
                out[i] = (self.rgba[i] * alpha + br * inv) // 255
                out[i + 1] = (self.rgba[i + 1] * alpha + bg * inv) // 255
                out[i + 2] = (self.rgba[i + 2] * alpha + bb * inv) // 255
                out[i + 3] = 255
        return bytes(out)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _mat_vec(matrix: Matrix3, vector: Vec3) -> Vec3:
    return (
        vector[0] * matrix[0][0] + vector[1] * matrix[1][0] + vector[2] * matrix[2][0],
        vector[0] * matrix[0][1] + vector[1] * matrix[1][1] + vector[2] * matrix[2][1],
        vector[0] * matrix[0][2] + vector[1] * matrix[1][2] + vector[2] * matrix[2][2],
    )


def _apply_view(coord: Vec3, view: ViewSnapshot) -> Vec3:
    transformed = _mat_vec(view.rotation, coord)
    return (
        transformed[0] + view.translation[0],
        transformed[1] + view.translation[1],
        transformed[2] + view.translation[2],
    )


def _center_viewed_coordinates(atoms: Sequence[AtomRecord], view: ViewSnapshot) -> Tuple[Vec3, float]:
    transformed = [_mat_vec(view.rotation, atom.coord) for atom in atoms]
    if not transformed:
        return (0.0, 0.0, 0.0), 1.0
    xmin = min(p[0] for p in transformed)
    xmax = max(p[0] for p in transformed)
    ymin = min(p[1] for p in transformed)
    ymax = max(p[1] for p in transformed)
    zmin = min(p[2] for p in transformed)
    zmax = max(p[2] for p in transformed)
    max_radius = max(max(0.0, atom.radius) for atom in atoms) * view.pixels_per_angstrom
    if view.auto_center:
        # Matches the original auto-center behavior: x/y centered and the
        # highest atom placed just behind the z=0 image plane.
        center = (-(xmin + xmax) / 2.0, -(ymin + ymax) / 2.0, -zmax - max_radius / max(view.pixels_per_angstrom, 1e-9) - 1.0)
    else:
        center = (0.0, 0.0, 0.0)
    return center, zmax - zmin


@lru_cache(maxsize=128)
def _sphere_points(radius: float) -> Tuple[Tuple[int, int, float], ...]:
    """Return the raster samples for a sphere radius.

    Molecular scenes normally contain only a handful of distinct atom radii.
    Reusing their integer sphere tables avoids rebuilding the same, increasingly
    large table for every atom during high-resolution exports.
    """

    radius = max(0.0, radius)
    limit = int(radius)
    points: List[Tuple[int, int, float]] = []
    for dx in range(-limit - 1, limit + 2):
        for dy in range(-limit - 1, limit + 2):
            distance = math.sqrt(float(dx * dx + dy * dy))
            if distance <= radius:
                points.append((dx, dy, math.sqrt(max(0.0, radius * radius - distance * distance))))
    return tuple(points)


@lru_cache(maxsize=128)
def _sphere_arrays(radius: float):
    """Return cached NumPy arrays for vectorized sphere rasterization."""

    points = _sphere_points(radius)
    if not points:
        return (
            _np.empty(0, dtype=_np.int32),
            _np.empty(0, dtype=_np.int32),
            _np.empty(0, dtype=_np.float64),
        )
    offsets_x, offsets_y, surface_z = zip(*points)
    return (
        _np.asarray(offsets_x, dtype=_np.int32),
        _np.asarray(offsets_y, dtype=_np.int32),
        _np.asarray(surface_z, dtype=_np.float64),
    )


def _safe_ramp(value: float, low: float, high: float) -> float:
    if high <= low:
        return 1.0 if value > low else 0.0
    return _clamp((value - low) / (high - low))


def _contour_thresholds(style: IllustrationStyle) -> Tuple[float, float]:
    """Return thresholds calibrated to the selected contour kernel.

    Kernels 3 and 4 accumulate normalized depth differences rather than the
    pixel-valued derivative returned by kernels 1 and 2.  Their raw response
    ranges are therefore different even though the UI exposes one pair of
    contour thresholds.  The factors preserve the same practical control
    range while retaining the original kernel shapes.
    """

    response_scale = {3: 0.5, 4: 2.0}.get(style.contour_kernel, 1.0)
    return style.contour_low * response_scale, style.contour_high * response_scale


def _kernel_value(kind: int, depth: List[List[float]], x: int, y: int, cx: int, cy: int,
                  depth_min: float, depth_max: float, step: int = 1) -> float:
    if kind == 1:
        weights = (
            (-0.8, -1.0, -0.8),
            (-1.0, 7.2, -1.0),
            (-0.8, -1.0, -0.8),
        )
        total = 0.0
        for ix in range(3):
            for iy in range(3):
                total += weights[ix][iy] * depth[x + (ix - 1) * step][y + (iy - 1) * step]
        return abs(total / 3.0)
    if kind == 2:
        total = 0.0
        weights = {
            (-1, -1): -0.8, (-1, 0): -1.0, (-1, 1): -0.8,
            (0, -1): -1.0, (0, 0): 8.8, (0, 1): -1.0,
            (1, -1): -0.8, (1, 0): -1.0, (1, 1): -0.8,
            (-2, -1): -0.1, (-2, 0): -0.2, (-2, 1): -0.1,
            (2, -1): -0.1, (2, 0): -0.2, (2, 1): -0.1,
            (-1, -2): -0.1, (0, -2): -0.2, (1, -2): -0.1,
            (-1, 2): -0.1, (0, 2): -0.2, (1, 2): -0.1,
        }
        for (dx, dy), weight in weights.items():
            total += weight * depth[x + dx * step][y + dy * step]
        return abs(total / 3.0)
    total = 0.0
    for dx in range(-1 if kind == 3 else -2, 2 if kind == 3 else 3):
        for dy in range(-1 if kind == 3 else -2, 2 if kind == 3 else 3):
            if kind == 4 and abs(dx * dy) == 4:
                continue
            difference = abs(depth[cx][cy] - depth[cx + dx * step][cy + dy * step])
            if difference > depth_min:
                total += min((difference - depth_min) / max(depth_max - depth_min, 1e-9), 1.0)
    return total


def _outline_opacity(depth: List[List[float]], atom_map: List[List[int]], atoms: Sequence[AtomRecord],
                     x: int, y: int, style: IllustrationStyle) -> float:
    width = len(depth)
    height = len(depth[0]) if width else 0
    step = max(1, int(round(style.raster_scale)))
    # Kernel 2 is sampled one step around (x, y) and inspects another two
    # steps around each sample.  Count-based kernels use (x, y) directly, so
    # the usual two-step group-boundary margin is sufficient for them.
    margin = (3 if style.contour_kernel == 2 else 2) * step
    if x < margin or y < margin or x >= width - margin or y >= height - margin:
        return 0.0

    current = atom_map[x][y]
    current_subunit = atoms[current].subunit if current >= 0 else None
    current_residue = atoms[current].residue if current >= 0 else None
    subunit_changes = 0
    residue_changes = 0
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            if abs(dx * dy) == 4:
                continue
            neighbor = atom_map[x + dx * step][y + dy * step]
            neighbor_subunit = atoms[neighbor].subunit if neighbor >= 0 else None
            neighbor_residue = atoms[neighbor].residue if neighbor >= 0 else None
            if current_subunit != neighbor_subunit:
                subunit_changes += 1
            if current_residue is not None and neighbor_residue is not None:
                if abs(current_residue - neighbor_residue) > style.residue_difference:
                    residue_changes += 1

    subunit_opacity = min(_safe_ramp(subunit_changes, style.subunit_low, style.subunit_high), 1.0)
    residue_opacity = min(_safe_ramp(residue_changes, style.residue_low, style.residue_high), 1.0)
    group_opacity = max(subunit_opacity, residue_opacity, 0.0)

    local_values: List[float] = []
    active_count = 0
    contour_low, contour_high = _contour_thresholds(style)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            value = _kernel_value(
                style.contour_kernel, depth, x + dx * step, y + dy * step, x, y,
                style.contour_depth_min, style.contour_depth_max,
                step,
            )
            local = _clamp(_safe_ramp(value, contour_low, contour_high))
            local_values.append(local)
            if local > 0.0:
                active_count += 1
    if active_count >= 6:
        # Match Illustrate's original normalization: the nine samples are
        # averaged over the six-sample activation threshold, not over all
        # nine positions.  This keeps kernels 3 and 4 from becoming
        # artificially faint when several neighboring derivatives are active.
        contour_opacity = sum(local_values) / 6.0
    else:
        contour_opacity = local_values[4]
    return max(group_opacity, _clamp(contour_opacity))


def _render_python(scene: RenderScene, view: ViewSnapshot, style: IllustrationStyle,
                   width: int, height: int) -> RenderedImage:
    """Render a scene to an RGBA image.

    The implementation intentionally uses Python lists so it can be tested in
    a plain Python installation.  ChimeraX bundles NumPy, and this function's
    immutable input/output contract is designed so a NumPy implementation can
    replace the inner loops without changing the tool API.
    """

    width = max(2, int(width))
    height = max(2, int(height))
    radius_scale = max(0.0, view.pixels_per_angstrom * style.radius_scale)

    center, _ = _center_viewed_coordinates(scene.atoms, view)
    projected: List[Tuple[float, float, float, float, AtomRecord]] = []
    for atom in scene.atoms:
        transformed = _mat_vec(view.rotation, atom.coord)
        if view.auto_center:
            transformed = (
                transformed[0] + center[0],
                transformed[1] + center[1],
                transformed[2] + center[2],
            )
        else:
            transformed = (
                transformed[0] + view.translation[0],
                transformed[1] + view.translation[1],
                transformed[2] + view.translation[2],
            )
        projected.append((
            transformed[0] * view.pixels_per_angstrom + width / 2.0,
            transformed[1] * view.pixels_per_angstrom + height / 2.0,
            transformed[2] * view.pixels_per_angstrom,
            max(0.0, atom.radius) * radius_scale,
            atom,
        ))

    # The view translation is in world coordinates and can put the whole
    # molecule well behind the camera after a rotation.  A fixed depth
    # sentinel then becomes larger than every projected atom at high output
    # scales, so no sphere can overwrite the background.  Keep the sentinel
    # just behind this particular projection instead.
    depth_floor = min(
        (pz - radius for _px, _py, pz, radius, _atom in projected
         if pz < 0.0 and radius > 0.0),
        default=-10000.0,
    ) - 1.0
    depth = [[depth_floor for _ in range(height)] for _ in range(width)]
    atom_map = [[-1 for _ in range(height)] for _ in range(width)]

    for atom_index, (px, py, pz, radius, _atom) in enumerate(projected):
        if pz >= 0.0 or radius <= 0.0:
            continue
        for dx, dy, surface_z in _sphere_points(radius):
            x = int(px + dx)
            y = int(py + dy)
            if x < 0 or x >= width or y < 0 or y >= height:
                continue
            z = surface_z + pz
            if z > depth[x][y]:
                depth[x][y] = z
                atom_map[x][y] = atom_index

    visible_depths = [depth[x][y] for x in range(width) for y in range(height) if atom_map[x][y] >= 0]
    if visible_depths:
        zmin = min(visible_depths)
        zmax = min(max(visible_depths), 0.0)
    else:
        zmin = 0.0
        zmax = 0.0
    zspread = zmax - zmin
    if zspread <= 1e-9:
        zspread = 1.0

    shadow_offsets = []
    if style.shadows:
        shadow_radius = max(1, int(round(50.0 * style.raster_scale)))
        shadow_step = max(1, int(round(5.0 * style.raster_scale)))
        for dx in range(-shadow_radius, shadow_radius + 1, shadow_step):
            for dy in range(-shadow_radius, shadow_radius + 1, shadow_step):
                distance = math.sqrt(float(dx * dx + dy * dy))
                if distance <= 50.0 and (dx != 0 or dy != 0):
                    shadow_offsets.append((dx, dy, distance))

    output = bytearray(width * height * 4)
    for x in range(width):
        for y in range(height):
            atom_index = atom_map[x][y]
            z = min(depth[x][y], 0.0)
            shadow = 1.0
            if atom_index >= 0 and style.shadows:
                for dx, dy, distance in shadow_offsets:
                    nx = x + dx
                    ny = y + dy
                    if 0 <= nx < width and 0 <= ny < height:
                        z_difference = depth[nx][ny] - depth[x][y]
                        if z_difference > style.shadow_depth and distance * style.shadow_cone_angle < z_difference + style.shadow_depth:
                            shadow -= style.shadow_contribution
                shadow = max(shadow, style.shadow_maximum)

            fog_fraction = style.fog_front - (zmax - z) / zspread * (style.fog_front - style.fog_back)
            if z < zmin:
                fog_fraction = 1.0
            fog_fraction = _clamp(fog_fraction)
            if atom_index >= 0:
                color = scene.atoms[atom_index].color
            else:
                color = style.background
            base_rgb = tuple(
                _clamp(fog_fraction * shadow * color[i] + (1.0 - fog_fraction) * style.fog_color[i])
                for i in range(3)
            )
            outline_opacity = 0.0
            if style.contour_kernel in (1, 2, 3, 4):
                outline_opacity = _outline_opacity(depth, atom_map, scene.atoms, x, y, style)
            # Illustrate writes the outline as a blackening of the pixel's
            # color, while its separate opacity map controls transparency.
            rgb = tuple(_clamp((1.0 - outline_opacity) * value) for value in base_rgb)
            opacity = max(1.0 if atom_index >= 0 else 0.0, outline_opacity)
            index = (y * width + x) * 4
            output[index:index + 4] = bytes((
                int(round(rgb[0] * 255.0)),
                int(round(rgb[1] * 255.0)),
                int(round(rgb[2] * 255.0)),
                int(round(_clamp(opacity) * 255.0)),
            ))
    return RenderedImage(width, height, bytes(output), style.background)


def _numpy_shift(array, dx: int, dy: int, fill_value):
    """Return ``array[y + dy, x + dx]`` with a constant outside the frame."""

    height, width = array.shape
    shifted = _np.full_like(array, fill_value)
    source_y0 = max(0, dy)
    source_y1 = min(height, height + dy)
    source_x0 = max(0, dx)
    source_x1 = min(width, width + dx)
    dest_y0 = max(0, -dy)
    dest_y1 = min(height, height - dy)
    dest_x0 = max(0, -dx)
    dest_x1 = min(width, width - dx)
    if source_y1 > source_y0 and source_x1 > source_x0:
        shifted[dest_y0:dest_y1, dest_x0:dest_x1] = array[source_y0:source_y1, source_x0:source_x1]
    return shifted


def _numpy_shift_region(array, x0: int, x1: int, y0: int, y1: int,
                        dx: int, dy: int, fill_value):
    """Return a shifted image region without allocating a full-frame array."""

    height = y1 - y0
    width = x1 - x0
    shifted = _np.full((height, width), fill_value, dtype=array.dtype)
    source_x0 = max(0, x0 + dx)
    source_x1 = min(array.shape[1], x1 + dx)
    source_y0 = max(0, y0 + dy)
    source_y1 = min(array.shape[0], y1 + dy)
    if source_x1 <= source_x0 or source_y1 <= source_y0:
        return shifted
    dest_x0 = source_x0 - (x0 + dx)
    dest_x1 = source_x1 - (x0 + dx)
    dest_y0 = source_y0 - (y0 + dy)
    dest_y1 = source_y1 - (y0 + dy)
    shifted[dest_y0:dest_y1, dest_x0:dest_x1] = array[source_y0:source_y1, source_x0:source_x1]
    return shifted


def _numpy_offset_slices(frame_width: int, frame_height: int,
                         x0: int, x1: int, y0: int, y1: int,
                         dx: int, dy: int):
    """Return destination/source slices for ``source[y+dy, x+dx]``.

    Unlike the shift helpers, this allocates no temporary image.  It is useful
    for shadow accumulation, where out-of-frame samples can never cast a
    shadow and therefore do not need a filled array.
    """

    dest_x0 = max(x0, -dx)
    dest_x1 = min(x1, frame_width - dx)
    dest_y0 = max(y0, -dy)
    dest_y1 = min(y1, frame_height - dy)
    if dest_x1 <= dest_x0 or dest_y1 <= dest_y0:
        return None
    destination = (
        slice(dest_y0 - y0, dest_y1 - y0),
        slice(dest_x0 - x0, dest_x1 - x0),
    )
    source = (
        slice(dest_y0 + dy, dest_y1 + dy),
        slice(dest_x0 + dx, dest_x1 + dx),
    )
    return destination, source


def _shadow_offsets(style: IllustrationStyle):
    shadow_radius = max(1, int(round(50.0 * style.raster_scale)))
    shadow_step = max(1, int(round(5.0 * style.raster_scale)))
    offsets = []
    for dx in range(-shadow_radius, shadow_radius + 1, shadow_step):
        for dy in range(-shadow_radius, shadow_radius + 1, shadow_step):
            if dx == 0 and dy == 0:
                continue
            distance = math.sqrt(float(dx * dx + dy * dy))
            if distance <= float(shadow_radius):
                offsets.append((dx, dy, distance))
    return offsets


def _numpy_shadow_rows(depth, visible, style: IllustrationStyle,
                       frame_width: int, frame_height: int,
                       tile_y0: int, local_y0: int, local_y1: int,
                       offsets):
    """Accumulate shadows for a row range while preserving sample order."""

    np = _np
    global_y0 = tile_y0 + local_y0
    global_y1 = tile_y0 + local_y1
    current_depth = depth[global_y0:global_y1, :]
    current_visible = visible[local_y0:local_y1, :]
    shadow_count = np.zeros(
        (local_y1 - local_y0, frame_width), dtype=np.float32
    )
    for dx, dy, distance in offsets:
        slices = _numpy_offset_slices(
            frame_width, frame_height,
            0, frame_width, global_y0, global_y1, dx, dy,
        )
        if slices is None:
            continue
        destination, source = slices
        difference = depth[source] - current_depth[destination]
        shadow_count[destination] += (
            current_visible[destination]
            & (difference > style.shadow_depth)
            & (distance * style.shadow_cone_angle
               < difference + style.shadow_depth)
        )
    return np.maximum(
        1.0 - shadow_count * style.shadow_contribution,
        style.shadow_maximum,
    )


def _numpy_shadow(depth, visible, style: IllustrationStyle, tile_y0: int = 0):
    """Compute soft shadows, splitting large frames over independent rows."""

    np = _np
    tile_height, frame_width = visible.shape
    frame_height = depth.shape[0]
    cacheable = (
        tile_y0 == 0
        and tile_height == frame_height
        and depth.size <= 1024 * 1024
    )
    owner = depth
    while isinstance(getattr(owner, "base", None), np.ndarray):
        owner = owner.base
    cache_key = (
        int(depth.__array_interface__["data"][0]),
        depth.shape,
        depth.strides,
        style.shadow_contribution,
        style.shadow_cone_angle,
        style.shadow_depth,
        style.shadow_maximum,
        style.raster_scale,
    )
    if cacheable:
        with _SHADOW_CACHE_LOCK:
            if (
                _SHADOW_CACHE["owner"] is owner
                and _SHADOW_CACHE["key"] == cache_key
            ):
                return _SHADOW_CACHE["shadow"]

    offsets = _shadow_offsets(style)
    # NumPy releases the GIL for these array operations.  Row partitions keep
    # each pixel's offset accumulation order unchanged while using multiple
    # cores and without duplicating full-frame buffers.
    max_workers = _SHADOW_WORKERS
    if tile_height * frame_width < 750_000 or max_workers == 1:
        shadow = _numpy_shadow_rows(
            depth, visible, style, frame_width, frame_height,
            tile_y0, 0, tile_height, offsets,
        )
    else:
        boundaries = [
            int(round(index * tile_height / max_workers))
            for index in range(max_workers + 1)
        ]
        shadow = np.empty((tile_height, frame_width), dtype=np.float32)
        jobs = []
        for index in range(max_workers):
            local_y0 = boundaries[index]
            local_y1 = boundaries[index + 1]
            if local_y1 <= local_y0:
                continue
            jobs.append((
                local_y0,
                local_y1,
                _SHADOW_EXECUTOR.submit(
                    _numpy_shadow_rows,
                    depth, visible, style, frame_width, frame_height,
                    tile_y0, local_y0, local_y1, offsets,
                ),
            ))
        for local_y0, local_y1, future in jobs:
            shadow[local_y0:local_y1, :] = future.result()
    if cacheable:
        with _SHADOW_CACHE_LOCK:
            _SHADOW_CACHE.update({
                "owner": owner,
                "key": cache_key,
                "shadow": shadow,
            })
    return shadow


def _expand_cropped_image(image: RenderedImage, full_width: int, full_height: int,
                          x0: int, y0: int) -> RenderedImage:
    """Place a processed crop back into its original transparent frame."""

    if (image.width, image.height) == (full_width, full_height):
        return image
    background = bytes(
        max(0, min(255, int(round(channel * 255.0))))
        for channel in image.background
    ) + b"\x00"
    background_row = background * full_width
    crop_stride = image.width * 4
    prefix = background * x0
    suffix = background * (full_width - x0 - image.width)
    chunks = [background_row] * y0
    for row in range(image.height):
        source_start = row * crop_stride
        chunks.extend((
            prefix,
            image.rgba[source_start:source_start + crop_stride],
            suffix,
        ))
    chunks.extend(
        [background_row] * (full_height - y0 - image.height)
    )
    return RenderedImage(
        full_width, full_height, b"".join(chunks), image.background
    )


def _render_numpy_tiled(scene: RenderScene, view: ViewSnapshot, style: IllustrationStyle,
                        width: int, height: int, depth, atom_map,
                        zmin: float, zmax: float, depth_floor: float) -> RenderedImage:
    """Post-process a large depth buffer in row tiles.

    The 0.1.6 renderer is retained for normal-sized images.  At 8K, keeping
    every intermediate RGB, contour, and shifted-neighbor array at full
    resolution can require several gigabytes and leave the export blank after
    the worker runs out of memory.  This path applies the same formulas to
    512-row tiles while retaining the complete depth and atom maps needed for
    occlusion, contours, and shadows.
    """

    np = _np
    subunit_codes = []
    subunit_lookup = {}
    residue_numbers = []
    colors = []
    for atom in scene.atoms:
        if atom.subunit not in subunit_lookup:
            subunit_lookup[atom.subunit] = len(subunit_lookup) + 1
        subunit_codes.append(subunit_lookup[atom.subunit])
        residue_numbers.append(atom.residue)
        colors.append(atom.color)

    color_array = np.asarray(colors if colors else [(0.5, 0.5, 0.5)], dtype=np.float32)
    subunit_array = np.asarray(subunit_codes if subunit_codes else [0], dtype=np.int32)
    residue_array = np.asarray(residue_numbers if residue_numbers else [9999], dtype=np.int32)
    output = bytearray(width * height * 4)
    tile_rows = 512
    neighborhood_step = max(1, int(round(style.raster_scale)))
    neighborhood_margin = (3 if style.contour_kernel == 2 else 2) * neighborhood_step
    kernel_one = (
        (-0.8, -1.0, -0.8),
        (-1.0, 7.2, -1.0),
        (-0.8, -1.0, -0.8),
    )
    kernel_two = {
        (-1, -1): -0.8, (-1, 0): -1.0, (-1, 1): -0.8,
        (0, -1): -1.0, (0, 0): 8.8, (0, 1): -1.0,
        (1, -1): -0.8, (1, 0): -1.0, (1, 1): -0.8,
        (-2, -1): -0.1, (-2, 0): -0.2, (-2, 1): -0.1,
        (2, -1): -0.1, (2, 0): -0.2, (2, 1): -0.1,
        (-1, -2): -0.1, (0, -2): -0.2, (1, -2): -0.1,
        (-1, 2): -0.1, (0, 2): -0.2, (1, 2): -0.1,
    }

    for y0 in range(0, height, tile_rows):
        y1 = min(height, y0 + tile_rows)
        tile_height = y1 - y0
        influence_y0 = max(0, y0 - neighborhood_margin)
        influence_y1 = min(height, y1 + neighborhood_margin)
        if not np.any(atom_map[influence_y0:influence_y1, :] >= 0):
            background = bytes(
                max(0, min(255, int(round(channel * 255.0))))
                for channel in style.background
            ) + b"\x00"
            output[y0 * width * 4:y1 * width * 4] = (
                background * (tile_height * width)
            )
            continue
        tile_depth = depth[y0:y1, :]
        tile_atom_map = atom_map[y0:y1, :]
        visible = tile_atom_map >= 0
        shadow = np.ones((tile_height, width), dtype=np.float32)
        if style.shadows and visible.any():
            shadow = _numpy_shadow(depth, visible, style, tile_y0=y0)

        z = np.minimum(tile_depth, 0.0)
        fog_fraction = style.fog_front - (zmax - z) / max(zmax - zmin, 1e-9) * (style.fog_front - style.fog_back)
        fog_fraction = np.asarray(fog_fraction, dtype=np.float32)
        fog_fraction[tile_depth < zmin] = 1.0
        fog_fraction = np.clip(fog_fraction, 0.0, 1.0)

        safe_indices = np.maximum(tile_atom_map, 0)
        color_image = color_array[safe_indices]
        color_image = np.where(visible[..., None], color_image, np.asarray(style.background, dtype=np.float32))
        fog_color = np.asarray(style.fog_color, dtype=np.float32)
        rgb = fog_fraction[..., None] * shadow[..., None] * color_image + (1.0 - fog_fraction[..., None]) * fog_color

        current_subunit = np.where(visible, subunit_array[safe_indices], 9999)
        current_residue = np.where(visible, residue_array[safe_indices], 9999)
        subunit_changes = np.zeros((tile_height, width), dtype=np.float32)
        residue_changes = np.zeros((tile_height, width), dtype=np.float32)
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                if abs(dx * dy) == 4:
                    continue
                neighbor_map = _numpy_shift_region(
                    atom_map, 0, width, y0, y1,
                    dx * neighborhood_step, dy * neighborhood_step, -1
                )
                neighbor_visible = neighbor_map >= 0
                neighbor_indices = np.maximum(neighbor_map, 0)
                neighbor_subunit = np.where(neighbor_visible, subunit_array[neighbor_indices], 9999)
                neighbor_residue = np.where(neighbor_visible, residue_array[neighbor_indices], 9999)
                subunit_changes += current_subunit != neighbor_subunit
                residue_changes += (
                    visible
                    & (neighbor_residue != 9999)
                    & (np.abs(current_residue - neighbor_residue) > style.residue_difference)
                )
        interior = np.ones((tile_height, width), dtype=bool)
        interior[:, :neighborhood_margin] = False
        interior[:, width - neighborhood_margin:] = False
        if y0 < neighborhood_margin:
            interior[:neighborhood_margin - y0, :] = False
        if y1 > height - neighborhood_margin:
            interior[height - neighborhood_margin - y0:, :] = False
        subunit_opacity = np.clip(
            (subunit_changes - style.subunit_low) / max(style.subunit_high - style.subunit_low, 1e-9), 0.0, 1.0
        )
        residue_opacity = np.clip(
            (residue_changes - style.residue_low) / max(style.residue_high - style.residue_low, 1e-9), 0.0, 1.0
        )
        group_opacity = np.maximum(subunit_opacity, residue_opacity)
        group_opacity[~interior] = 0.0

        contour_opacity = np.zeros((tile_height, width), dtype=np.float32)
        if style.contour_kernel in (1, 2, 3, 4) and height > 2 * neighborhood_margin and width > 2 * neighborhood_margin:
            contour_low, contour_high = _contour_thresholds(style)
            contour_sum = np.zeros((tile_height, width), dtype=np.float32)
            active = np.zeros((tile_height, width), dtype=np.int8)
            center_value = np.zeros((tile_height, width), dtype=np.float32)
            local_offsets = (
                ((0, 0),)
                if style.contour_kernel in (3, 4)
                else tuple((x, y) for x in (-1, 0, 1) for y in (-1, 0, 1))
            )
            for local_x, local_y in local_offsets:
                if style.contour_kernel == 1:
                    raw = np.zeros((tile_height, width), dtype=np.float32)
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            raw += kernel_one[dy + 1][dx + 1] * _numpy_shift_region(
                                depth, 0, width, y0, y1,
                                (local_x + dx) * neighborhood_step,
                                (local_y + dy) * neighborhood_step,
                                depth_floor
                            )
                    raw = np.abs(raw / 3.0)
                elif style.contour_kernel == 2:
                    raw = np.zeros((tile_height, width), dtype=np.float32)
                    for (dx, dy), weight in kernel_two.items():
                        raw += weight * _numpy_shift_region(
                            depth, 0, width, y0, y1,
                            (local_x + dx) * neighborhood_step,
                            (local_y + dy) * neighborhood_step,
                            depth_floor
                        )
                    raw = np.abs(raw / 3.0)
                else:
                    raw = np.zeros((tile_height, width), dtype=np.float32)
                    offsets = range(-1, 2) if style.contour_kernel == 3 else range(-2, 3)
                    center_depth = _numpy_shift_region(
                        depth, 0, width, y0, y1,
                        0,
                        0,
                        depth_floor
                    )
                    for dx in offsets:
                        for dy in offsets:
                            if style.contour_kernel == 4 and abs(dx * dy) == 4:
                                continue
                            difference = np.abs(
                                center_depth - _numpy_shift_region(
                                    depth, 0, width, y0, y1,
                                    dx * neighborhood_step,
                                    dy * neighborhood_step,
                                    depth_floor
                                )
                            )
                            raw += np.where(
                                difference > style.contour_depth_min,
                                np.minimum(
                                    (difference - style.contour_depth_min)
                                    / max(style.contour_depth_max - style.contour_depth_min, 1e-9),
                                    1.0,
                                ),
                                0.0,
                            )
                value = np.clip(
                    (raw - contour_low) / max(contour_high - contour_low, 1e-9),
                    0.0, 1.0,
                )
                if style.contour_kernel in (3, 4):
                    # The original kernel ignores the outer 3x3 sample offset
                    # for count-based kernels, so all nine values are equal.
                    # Preserve its nine-sample/six-threshold normalization
                    # without recomputing the same depth differences nine times.
                    contour_sum = value * np.float32(9.0)
                    active = np.where(value > 0.0, 9, 0).astype(np.int8)
                    center_value = value
                else:
                    contour_sum += value
                    active += value > 0.0
                    if local_x == 0 and local_y == 0:
                        center_value = value
            core = np.where(active >= 6, contour_sum / np.float32(6.0), center_value)
            inner_top = max(0, neighborhood_margin - y0)
            inner_bottom = min(tile_height, height - neighborhood_margin - y0)
            if inner_bottom > inner_top:
                contour_opacity[inner_top:inner_bottom, neighborhood_margin:width - neighborhood_margin] = np.clip(
                    core[inner_top:inner_bottom, neighborhood_margin:width - neighborhood_margin], 0.0, 1.0
                )

        outline_opacity = np.maximum(group_opacity, contour_opacity)
        rgb = (1.0 - outline_opacity[..., None]) * rgb
        alpha = np.maximum(visible.astype(np.float32), outline_opacity)
        rgba = np.empty((tile_height, width, 4), dtype=np.uint8)
        rgba[..., :3] = np.clip(np.rint(rgb * 255.0), 0.0, 255.0).astype(np.uint8)
        rgba[..., 3] = np.clip(np.rint(alpha * 255.0), 0.0, 255.0).astype(np.uint8)
        output[y0 * width * 4:y1 * width * 4] = rgba.tobytes()

    return RenderedImage(width, height, bytes(output), style.background)


def _render_numpy(scene: RenderScene, view: ViewSnapshot, style: IllustrationStyle,
                  width: int, height: int) -> RenderedImage:
    """NumPy implementation used by ChimeraX for interactive preview speed."""

    np = _np
    full_width = width
    full_height = height
    center, _ = _center_viewed_coordinates(scene.atoms, view)
    projected = []
    subunit_codes = []
    subunit_lookup = {}
    residue_numbers = []
    colors = []
    radius_scale = max(0.0, view.pixels_per_angstrom * style.radius_scale)

    for index, atom in enumerate(scene.atoms):
        transformed = _mat_vec(view.rotation, atom.coord)
        if view.auto_center:
            transformed = tuple(transformed[i] + center[i] for i in range(3))
        else:
            transformed = tuple(transformed[i] + view.translation[i] for i in range(3))
        projected.append((
            transformed[0] * view.pixels_per_angstrom + width / 2.0,
            transformed[1] * view.pixels_per_angstrom + height / 2.0,
            transformed[2] * view.pixels_per_angstrom,
            max(0.0, atom.radius) * radius_scale,
        ))
        if atom.subunit not in subunit_lookup:
            subunit_lookup[atom.subunit] = len(subunit_lookup) + 1
        subunit_codes.append(subunit_lookup[atom.subunit])
        residue_numbers.append(atom.residue)
        colors.append(atom.color)

    # Depth values are multiplied by pixels_per_angstrom.  After a rotated
    # ChimeraX capture this can put every atom below the old fixed -10000
    # background at 6K/8K, making the rasterizer believe the frame is already
    # occupied by nearer background pixels.  Use a projection-relative floor.
    depth_floor = min(
        (pz - radius for _px, _py, pz, radius in projected
         if pz < 0.0 and radius > 0.0),
        default=-10000.0,
    ) - 1.0

    color_array = np.asarray(colors if colors else [(0.5, 0.5, 0.5)], dtype=np.float32)
    subunit_array = np.asarray(subunit_codes if subunit_codes else [0], dtype=np.int32)
    residue_array = np.asarray(residue_numbers if residue_numbers else [9999], dtype=np.int32)

    # Establish a conservative sphere-plus-neighborhood rectangle before
    # allocating the depth and atom-index buffers.  Sparse 6K/8K scenes often
    # occupy a small part of the frame, so allocating those two arrays only
    # for the active rectangle avoids hundreds of megabytes of transparent
    # temporary storage.  Sphere sampling coordinates remain in the original
    # full-frame system and are shifted only after integer truncation.
    raster_x0 = 0
    raster_y0 = 0
    raster_x1 = width
    raster_y1 = height
    active_projected = [
        projected_atom
        for projected_atom in projected
        if projected_atom[2] < 0.0 and projected_atom[3] > 0.0
    ]
    if active_projected:
        neighborhood_step = max(1, int(round(style.raster_scale)))
        padding = 6 * neighborhood_step
        candidate_x0 = max(0, int(math.floor(min(
            px - math.ceil(radius) - 2
            for px, _py, _pz, radius in active_projected
        ))) - padding)
        candidate_x1 = min(width, int(math.ceil(max(
            px + math.ceil(radius) + 2
            for px, _py, _pz, radius in active_projected
        ))) + padding + 1)
        candidate_y0 = max(0, int(math.floor(min(
            py - math.ceil(radius) - 2
            for _px, py, _pz, radius in active_projected
        ))) - padding)
        candidate_y1 = min(height, int(math.ceil(max(
            py + math.ceil(radius) + 2
            for _px, py, _pz, radius in active_projected
        ))) + padding + 1)
        candidate_area = (
            (candidate_x1 - candidate_x0)
            * (candidate_y1 - candidate_y0)
        )
        if (
            candidate_x1 > candidate_x0
            and candidate_y1 > candidate_y0
            and candidate_area < width * height * 0.9
        ):
            raster_x0 = candidate_x0
            raster_x1 = candidate_x1
            raster_y0 = candidate_y0
            raster_y1 = candidate_y1

    cache_key = (
        view,
        full_width,
        full_height,
        style.radius_scale,
        raster_x0,
        raster_y0,
        raster_x1,
        raster_y1,
    )
    cacheable = full_width <= 1024 and full_height <= 1024
    with _RASTER_CACHE_LOCK:
        cache_hit = (
            cacheable
            and _RASTER_CACHE["scene"] is scene
            and _RASTER_CACHE["key"] == cache_key
        )
        if cache_hit:
            depth = _RASTER_CACHE["depth"]
            atom_map = _RASTER_CACHE["atom_map"]
    if not cache_hit:
        raster_width = raster_x1 - raster_x0
        raster_height = raster_y1 - raster_y0
        depth = np.full(
            (raster_height, raster_width), depth_floor, dtype=np.float32
        )
        atom_map = np.full(
            (raster_height, raster_width), -1, dtype=np.int32
        )
        # Use the same integer sphere table and ``int(center + offset)``
        # mapping as Illustrate's original Fortran rasterizer.  A continuous
        # disk mask changes the depth buffer at atom edges and therefore the
        # downstream illustration style.
        for atom_index, (px, py, pz, radius) in enumerate(projected):
            if pz >= 0.0 or radius <= 0.0:
                continue
            offsets_x, offsets_y, surface_z = _sphere_arrays(radius)
            x = np.trunc(px + offsets_x).astype(np.intp)
            y = np.trunc(py + offsets_y).astype(np.intp)
            inside = (
                (x >= raster_x0)
                & (x < raster_x1)
                & (y >= raster_y0)
                & (y < raster_y1)
            )
            if not inside.all():
                x = x[inside]
                y = y[inside]
                surface_z = surface_z[inside]
            x = x - raster_x0
            y = y - raster_y0
            z = surface_z + pz
            nearer = z > depth[y, x]
            if nearer.any():
                x = x[nearer]
                y = y[nearer]
                depth[y, x] = z[nearer]
                atom_map[y, x] = atom_index
        if cacheable:
            with _RASTER_CACHE_LOCK:
                _RASTER_CACHE.update({
                    "scene": scene,
                    "key": cache_key,
                    "depth": depth,
                    "atom_map": atom_map,
                    "origin": (raster_x0, raster_y0),
                })

    height, width = depth.shape
    visible = atom_map >= 0
    visible_depths = depth[visible]
    if visible_depths.size:
        zmin = float(visible_depths.min())
        zmax = min(float(visible_depths.max()), 0.0)
    else:
        zmin = 0.0
        zmax = 0.0
    zspread = max(zmax - zmin, 1e-9)

    crop_x0 = raster_x0
    crop_y0 = raster_y0
    if visible.any():
        visible_rows = np.flatnonzero(np.any(visible, axis=1))
        visible_columns = np.flatnonzero(np.any(visible, axis=0))
        neighborhood_step = max(1, int(round(style.raster_scale)))
        crop_padding = 6 * neighborhood_step
        crop_x0 = max(0, int(visible_columns[0]) - crop_padding)
        crop_x1 = min(width, int(visible_columns[-1]) + crop_padding + 1)
        crop_y0 = max(0, int(visible_rows[0]) - crop_padding)
        crop_y1 = min(height, int(visible_rows[-1]) + crop_padding + 1)
        crop_area = (crop_x1 - crop_x0) * (crop_y1 - crop_y0)
        if crop_area < width * height * 0.9:
            depth = depth[crop_y0:crop_y1, crop_x0:crop_x1]
            atom_map = atom_map[crop_y0:crop_y1, crop_x0:crop_x1]
            visible = atom_map >= 0
            height, width = depth.shape
            crop_x0 += raster_x0
            crop_y0 += raster_y0
        else:
            crop_x0 = raster_x0
            crop_y0 = raster_y0

    if width > 4096 or height > 4096:
        image = _render_numpy_tiled(
            scene, view, style, width, height, depth, atom_map, zmin, zmax, depth_floor
        )
        return _expand_cropped_image(
            image, full_width, full_height, crop_x0, crop_y0
        )

    shadow = np.ones((height, width), dtype=np.float32)
    if style.shadows and visible.any():
        shadow = _numpy_shadow(depth, visible, style)

    z = np.minimum(depth, 0.0)
    fog_fraction = style.fog_front - (zmax - z) / zspread * (style.fog_front - style.fog_back)
    fog_fraction = np.asarray(fog_fraction, dtype=np.float32)
    fog_fraction[depth < zmin] = 1.0
    fog_fraction = np.clip(fog_fraction, 0.0, 1.0)

    safe_indices = np.maximum(atom_map, 0)
    color_image = color_array[safe_indices]
    color_image = np.where(visible[..., None], color_image, np.asarray(style.background, dtype=np.float32))
    fog_color = np.asarray(style.fog_color, dtype=np.float32)
    rgb = fog_fraction[..., None] * shadow[..., None] * color_image + (1.0 - fog_fraction[..., None]) * fog_color

    # Subunit/residue boundary opacity.  The original uses a 5x5 cross-shaped
    # neighborhood; shifts make the same calculation vectorized.
    current_subunit = np.where(visible, subunit_array[safe_indices], 9999)
    current_residue = np.where(visible, residue_array[safe_indices], 9999)
    subunit_changes = np.zeros((height, width), dtype=np.float32)
    residue_changes = np.zeros((height, width), dtype=np.float32)
    neighborhood_step = max(1, int(round(style.raster_scale)))
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            if abs(dx * dy) == 4:
                continue
            neighbor_subunit = _numpy_shift(
                current_subunit, dx * neighborhood_step, dy * neighborhood_step, 9999
            )
            neighbor_residue = _numpy_shift(
                current_residue, dx * neighborhood_step, dy * neighborhood_step, 9999
            )
            subunit_changes += current_subunit != neighbor_subunit
            residue_changes += (
                visible
                & (neighbor_residue != 9999)
                & (np.abs(current_residue - neighbor_residue) > style.residue_difference)
            )
    interior = np.zeros((height, width), dtype=bool)
    neighborhood_margin = (3 if style.contour_kernel == 2 else 2) * neighborhood_step
    if height > 2 * neighborhood_margin and width > 2 * neighborhood_margin:
        interior[neighborhood_margin:height - neighborhood_margin,
                 neighborhood_margin:width - neighborhood_margin] = True
    subunit_opacity = np.clip(
        (subunit_changes - style.subunit_low) / max(style.subunit_high - style.subunit_low, 1e-9), 0.0, 1.0
    )
    residue_opacity = np.clip(
        (residue_changes - style.residue_low) / max(style.residue_high - style.residue_low, 1e-9), 0.0, 1.0
    )
    group_opacity = np.maximum(subunit_opacity, residue_opacity)
    group_opacity[~interior] = 0.0

    contour_opacity = np.zeros((height, width), dtype=np.float32)
    if style.contour_kernel in (1, 2, 3, 4) and height > 2 * neighborhood_margin and width > 2 * neighborhood_margin:
        contour_low, contour_high = _contour_thresholds(style)
        values = []
        contour_pad = 4 * neighborhood_step
        padded_depth = np.pad(depth, contour_pad, mode="constant", constant_values=depth_floor)
        contour_inner = neighborhood_margin
        kernel_one = (
            (-0.8, -1.0, -0.8),
            (-1.0, 7.2, -1.0),
            (-0.8, -1.0, -0.8),
        )
        kernel_two = {
            (-1, -1): -0.8, (-1, 0): -1.0, (-1, 1): -0.8,
            (0, -1): -1.0, (0, 0): 8.8, (0, 1): -1.0,
            (1, -1): -0.8, (1, 0): -1.0, (1, 1): -0.8,
            (-2, -1): -0.1, (-2, 0): -0.2, (-2, 1): -0.1,
            (2, -1): -0.1, (2, 0): -0.2, (2, 1): -0.1,
            (-1, -2): -0.1, (0, -2): -0.2, (1, -2): -0.1,
            (-1, 2): -0.1, (0, 2): -0.2, (1, 2): -0.1,
        }
        local_offsets = (
            ((0, 0),)
            if style.contour_kernel in (3, 4)
            else tuple((x, y) for x in (-1, 0, 1) for y in (-1, 0, 1))
        )
        for local_x, local_y in local_offsets:
            y_start = contour_pad + contour_inner + local_y * neighborhood_step
            y_end = contour_pad + height - contour_inner + local_y * neighborhood_step
            x_start = contour_pad + contour_inner + local_x * neighborhood_step
            x_end = contour_pad + width - contour_inner + local_x * neighborhood_step
            if style.contour_kernel == 1:
                raw = np.zeros((height - 2 * contour_inner, width - 2 * contour_inner), dtype=np.float32)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        raw += kernel_one[dy + 1][dx + 1] * padded_depth[
                            y_start + dy * neighborhood_step:y_end + dy * neighborhood_step,
                            x_start + dx * neighborhood_step:x_end + dx * neighborhood_step,
                        ]
                raw = np.abs(raw / 3.0)
            elif style.contour_kernel == 2:
                raw = np.zeros((height - 2 * contour_inner, width - 2 * contour_inner), dtype=np.float32)
                for (dx, dy), weight in kernel_two.items():
                    raw += weight * padded_depth[
                        y_start + dy * neighborhood_step:y_end + dy * neighborhood_step,
                        x_start + dx * neighborhood_step:x_end + dx * neighborhood_step,
                    ]
                raw = np.abs(raw / 3.0)
            else:
                raw = np.zeros((height - 2 * contour_inner, width - 2 * contour_inner), dtype=np.float32)
                offsets = range(-1, 2) if style.contour_kernel == 3 else range(-2, 3)
                for dx in offsets:
                    for dy in offsets:
                        if style.contour_kernel == 4 and abs(dx * dy) == 4:
                            continue
                        difference = np.abs(
                            padded_depth[
                                contour_pad + contour_inner:contour_pad + height - contour_inner,
                                contour_pad + contour_inner:contour_pad + width - contour_inner,
                            ]
                            - padded_depth[
                                contour_pad + contour_inner + dy * neighborhood_step:
                                contour_pad + height - contour_inner + dy * neighborhood_step,
                                contour_pad + contour_inner + dx * neighborhood_step:
                                contour_pad + width - contour_inner + dx * neighborhood_step,
                            ]
                        )
                        raw += np.where(
                            difference > style.contour_depth_min,
                            np.minimum(
                                (difference - style.contour_depth_min)
                                / max(style.contour_depth_max - style.contour_depth_min, 1e-9),
                                1.0,
                            ),
                            0.0,
                        )
            values.append(np.clip(
                (raw - contour_low) / max(contour_high - contour_low, 1e-9),
                0.0, 1.0,
            ))
        if style.contour_kernel in (3, 4):
            center_value = values[0]
            core = np.where(
                center_value > 0.0,
                center_value * np.float32(1.5),
                center_value,
            )
        else:
            stacked = np.stack(values, axis=0)
            active = np.sum(stacked > 0.0, axis=0)
            core = np.where(active >= 6, np.sum(stacked, axis=0) / 6.0, stacked[4])
        contour_opacity[contour_inner:height - contour_inner,
                        contour_inner:width - contour_inner] = np.clip(core, 0.0, 1.0)

    outline_opacity = np.maximum(group_opacity, contour_opacity)
    # Match Illustrate's original output: outline opacity darkens the RGB
    # channels toward black and also contributes to the separate alpha map.
    rgb = (1.0 - outline_opacity[..., None]) * rgb
    alpha = np.maximum(visible.astype(np.float32), outline_opacity)
    rgba = np.empty((height, width, 4), dtype=np.uint8)
    rgba[..., :3] = np.clip(np.rint(rgb * 255.0), 0.0, 255.0).astype(np.uint8)
    rgba[..., 3] = np.clip(np.rint(alpha * 255.0), 0.0, 255.0).astype(np.uint8)
    image = RenderedImage(width, height, rgba.tobytes(), style.background)
    return _expand_cropped_image(
        image, full_width, full_height, crop_x0, crop_y0
    )


def render(scene: RenderScene, view: ViewSnapshot, style: IllustrationStyle,
           width: int, height: int) -> RenderedImage:
    width = max(2, int(width))
    height = max(2, int(height))
    if _np is not None:
        return _render_numpy(scene, view, style, width, height)
    return _render_python(scene, view, style, width, height)


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def _png_scanlines(image: RenderedImage, transparent: bool):
    """Yield PNG scanlines without constructing another full-frame image."""

    row_bytes = image.width * 4
    if transparent:
        for row in range(image.height):
            start = row * row_bytes
            yield b"\x00" + image.rgba[start:start + row_bytes]
        return

    br, bg, bb = (
        max(0, min(255, int(round(channel * 255.0))))
        for channel in image.background
    )
    if _np is not None:
        source = _np.frombuffer(image.rgba, dtype=_np.uint8).reshape(
            image.height, image.width, 4
        )
        background = _np.asarray((br, bg, bb), dtype=_np.uint16)
        for y0 in range(0, image.height, 256):
            y1 = min(image.height, y0 + 256)
            tile = source[y0:y1]
            alpha = tile[..., 3].astype(_np.uint16)
            inverse = 255 - alpha
            output = _np.empty(tile.shape, dtype=_np.uint8)
            output[..., :3] = (
                (
                    tile[..., :3].astype(_np.uint16) * alpha[..., None]
                    + background * inverse[..., None]
                )
                // 255
            ).astype(_np.uint8)
            output[..., 3] = 255
            data = output.tobytes()
            for row in range(y1 - y0):
                start = row * row_bytes
                yield b"\x00" + data[start:start + row_bytes]
        return

    for row in range(image.height):
        start = row * row_bytes
        source = image.rgba[start:start + row_bytes]
        output = bytearray(row_bytes)
        for index in range(0, row_bytes, 4):
            alpha = source[index + 3]
            inverse = 255 - alpha
            output[index] = (source[index] * alpha + br * inverse) // 255
            output[index + 1] = (
                source[index + 1] * alpha + bg * inverse
            ) // 255
            output[index + 2] = (
                source[index + 2] * alpha + bb * inverse
            ) // 255
            output[index + 3] = 255
        yield b"\x00" + bytes(output)


def _compressed_png_data(image: RenderedImage, transparent: bool):
    compressor = zlib.compressobj(_PNG_COMPRESSION_LEVEL)
    compressed = bytearray()
    for scanline in _png_scanlines(image, transparent):
        compressed.extend(compressor.compress(scanline))
    compressed.extend(compressor.flush())
    return bytes(compressed)


def encode_png(image: RenderedImage, transparent: bool = True) -> bytes:
    """Encode an RGBA image as a lossless PNG."""

    compressed = _compressed_png_data(image, transparent)
    header = struct.pack(">IIBBBBB", image.width, image.height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )


def save_png(path: str, image: RenderedImage, transparent: bool = True) -> None:
    """Write a lossless PNG while keeping high-resolution memory bounded."""

    header = struct.pack(
        ">IIBBBBB", image.width, image.height, 8, 6, 0, 0, 0
    )
    with open(path, "wb") as output:
        output.write(b"\x89PNG\r\n\x1a\n")
        output.write(_png_chunk(b"IHDR", header))
        compressor = zlib.compressobj(_PNG_COMPRESSION_LEVEL)
        compressed = bytearray()
        for scanline in _png_scanlines(image, transparent):
            compressed.extend(compressor.compress(scanline))
            if len(compressed) >= _PNG_IDAT_CHUNK_SIZE:
                output.write(_png_chunk(b"IDAT", bytes(compressed)))
                compressed.clear()
        compressed.extend(compressor.flush())
        if compressed:
            output.write(_png_chunk(b"IDAT", bytes(compressed)))
        output.write(_png_chunk(b"IEND", b""))

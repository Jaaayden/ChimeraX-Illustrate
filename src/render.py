"""Pure-Python implementation of the Illustrate raster rendering pipeline.

The original project uses a fixed-size Fortran frame buffer and PPM output.  This
module keeps the same units and the same order of operations, while representing
the input as immutable Python data so it can be rendered outside ChimeraX's UI
thread. NumPy is optional for the core implementation and supplies the
accelerated backend when available; the public data model is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import struct
from typing import Iterable, List, Optional, Sequence, Tuple
import zlib

try:
    import numpy as _np
except ImportError:  # The renderer remains testable without ChimeraX/NumPy.
    _np = None


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
    shadow_maximum: float = 0.2
    contour_low: float = 3.0
    contour_high: float = 10.0
    contour_kernel: int = 1
    contour_depth_min: float = 0.0
    contour_depth_max: float = 5.0
    subunit_low: float = 3.0
    subunit_high: float = 10.0
    residue_low: float = 3.0
    residue_high: float = 8.0
    residue_difference: float = 6000.0
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
    return replace(
        style,
        contour_low=style.contour_low * scale,
        contour_high=style.contour_high * scale,
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


def _sphere_points(radius: float) -> List[Tuple[int, int, float]]:
    radius = max(0.0, radius)
    limit = int(radius)
    points: List[Tuple[int, int, float]] = []
    for dx in range(-limit - 1, limit + 2):
        for dy in range(-limit - 1, limit + 2):
            distance = math.sqrt(float(dx * dx + dy * dy))
            if distance <= radius:
                points.append((dx, dy, math.sqrt(max(0.0, radius * radius - distance * distance))))
    return points


def _safe_ramp(value: float, low: float, high: float) -> float:
    if high <= low:
        return 1.0 if value > low else 0.0
    return _clamp((value - low) / (high - low))


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
    margin = 2 * step
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
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            value = _kernel_value(
                style.contour_kernel, depth, x + dx * step, y + dy * step, x, y,
                style.contour_depth_min, style.contour_depth_max,
                step,
            )
            local = _clamp(_safe_ramp(value, style.contour_low, style.contour_high))
            local_values.append(local)
            if local > 0.0:
                active_count += 1
    if active_count >= 6:
        contour_opacity = sum(local_values) / float(len(local_values))
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
    neighborhood_margin = 2 * neighborhood_step
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
        tile_depth = depth[y0:y1, :]
        tile_atom_map = atom_map[y0:y1, :]
        visible = tile_atom_map >= 0
        shadow = np.ones((tile_height, width), dtype=np.float32)
        if style.shadows and visible.any():
            shadow_count = np.zeros((tile_height, width), dtype=np.float32)
            shadow_radius = max(1, int(round(50.0 * style.raster_scale)))
            shadow_step = max(1, int(round(5.0 * style.raster_scale)))
            for dx in range(-shadow_radius, shadow_radius + 1, shadow_step):
                for dy in range(-shadow_radius, shadow_radius + 1, shadow_step):
                    if dx == 0 and dy == 0:
                        continue
                    distance = math.sqrt(float(dx * dx + dy * dy))
                    if distance > float(shadow_radius):
                        continue
                    neighbor_depth = _numpy_shift_region(
                        depth, 0, width, y0, y1, dx, dy, depth_floor
                    )
                    difference = neighbor_depth - tile_depth
                    shadow_count += (
                        visible
                        & (difference > style.shadow_depth)
                        & (distance * style.shadow_cone_angle < difference + style.shadow_depth)
                    )
            shadow = np.maximum(1.0 - shadow_count * style.shadow_contribution, style.shadow_maximum)

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
            contour_sum = np.zeros((tile_height, width), dtype=np.float32)
            active = np.zeros((tile_height, width), dtype=np.int8)
            center_value = np.zeros((tile_height, width), dtype=np.float32)
            for local_x in (-1, 0, 1):
                for local_y in (-1, 0, 1):
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
                            local_x * neighborhood_step,
                            local_y * neighborhood_step,
                            depth_floor
                        )
                        for dx in offsets:
                            for dy in offsets:
                                if style.contour_kernel == 4 and abs(dx * dy) == 4:
                                    continue
                                difference = np.abs(
                                    center_depth - _numpy_shift_region(
                                    depth, 0, width, y0, y1,
                                        (local_x + dx) * neighborhood_step,
                                        (local_y + dy) * neighborhood_step,
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
                        (raw - style.contour_low) / max(style.contour_high - style.contour_low, 1e-9),
                        0.0, 1.0,
                    )
                    contour_sum += value
                    active += value > 0.0
                    if local_x == 0 and local_y == 0:
                        center_value = value
            core = np.where(active >= 6, contour_sum / 9.0, center_value)
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
    depth = np.full((height, width), -10000.0, dtype=np.float32)
    atom_map = np.full((height, width), -1, dtype=np.int32)
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
    depth.fill(depth_floor)

    color_array = np.asarray(colors if colors else [(0.5, 0.5, 0.5)], dtype=np.float32)
    subunit_array = np.asarray(subunit_codes if subunit_codes else [0], dtype=np.int32)
    residue_array = np.asarray(residue_numbers if residue_numbers else [9999], dtype=np.int32)

    for atom_index, (px, py, pz, radius) in enumerate(projected):
        if pz >= 0.0 or radius <= 0.0:
            continue
        x0 = max(0, int(math.floor(px - radius)) - 1)
        x1 = min(width, int(math.ceil(px + radius)) + 2)
        y0 = max(0, int(math.floor(py - radius)) - 1)
        y1 = min(height, int(math.ceil(py + radius)) + 2)
        if x1 <= x0 or y1 <= y0:
            continue
        yy, xx = np.ogrid[y0:y1, x0:x1]
        dx = xx.astype(np.float32) - px
        dy = yy.astype(np.float32) - py
        distance_squared = dx * dx + dy * dy
        mask = distance_squared <= radius * radius
        surface = np.sqrt(np.maximum(0.0, radius * radius - distance_squared)) + pz
        region_depth = depth[y0:y1, x0:x1]
        region_map = atom_map[y0:y1, x0:x1]
        update = mask & (surface > region_depth)
        region_depth[update] = surface[update]
        region_map[update] = atom_index

    visible = atom_map >= 0
    visible_depths = depth[visible]
    if visible_depths.size:
        zmin = float(visible_depths.min())
        zmax = min(float(visible_depths.max()), 0.0)
    else:
        zmin = 0.0
        zmax = 0.0
    zspread = max(zmax - zmin, 1e-9)

    if width > 4096 or height > 4096:
        return _render_numpy_tiled(
            scene, view, style, width, height, depth, atom_map, zmin, zmax, depth_floor
        )

    shadow = np.ones((height, width), dtype=np.float32)
    if style.shadows and visible.any():
        shadow_count = np.zeros((height, width), dtype=np.float32)
        shadow_radius = max(1, int(round(50.0 * style.raster_scale)))
        shadow_step = max(1, int(round(5.0 * style.raster_scale)))
        for dx in range(-shadow_radius, shadow_radius + 1, shadow_step):
            for dy in range(-shadow_radius, shadow_radius + 1, shadow_step):
                if dx == 0 and dy == 0:
                    continue
                distance = math.sqrt(float(dx * dx + dy * dy))
                if distance > float(shadow_radius):
                    continue
                neighbor_depth = _numpy_shift(depth, dx, dy, depth_floor)
                difference = neighbor_depth - depth
                shadow_count += (
                    visible
                    & (difference > style.shadow_depth)
                    & (distance * style.shadow_cone_angle < difference + style.shadow_depth)
                )
        shadow = np.maximum(1.0 - shadow_count * style.shadow_contribution, style.shadow_maximum)

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
    neighborhood_margin = 2 * neighborhood_step
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
        for local_x in (-1, 0, 1):
            for local_y in (-1, 0, 1):
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
                                padded_depth[y_start:y_end, x_start:x_end]
                                - padded_depth[
                                    y_start + dy * neighborhood_step:y_end + dy * neighborhood_step,
                                    x_start + dx * neighborhood_step:x_end + dx * neighborhood_step,
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
                    (raw - style.contour_low) / max(style.contour_high - style.contour_low, 1e-9),
                    0.0, 1.0,
                ))
        stacked = np.stack(values, axis=0)
        active = np.sum(stacked > 0.0, axis=0)
        core = np.where(active >= 6, np.mean(stacked, axis=0), stacked[4])
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
    return RenderedImage(width, height, rgba.tobytes(), style.background)


def render(scene: RenderScene, view: ViewSnapshot, style: IllustrationStyle,
           width: int, height: int) -> RenderedImage:
    width = max(2, int(width))
    height = max(2, int(height))
    if _np is not None:
        return _render_numpy(scene, view, style, width, height)
    return _render_python(scene, view, style, width, height)


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def encode_png(image: RenderedImage, transparent: bool = True) -> bytes:
    """Encode an RGBA image as PNG using only Python's standard library."""

    rgba = image.composited_rgba(transparent=transparent)
    row_bytes = image.width * 4
    compressor = zlib.compressobj(6)
    compressed = bytearray()
    for row in range(image.height):
        start = row * row_bytes
        # Feed one row at a time so an 8000x8000 export does not create a
        # second full-frame scanline buffer before compression.
        compressed.extend(compressor.compress(b"\x00" + rgba[start:start + row_bytes]))
    compressed.extend(compressor.flush())
    header = struct.pack(">IIBBBBB", image.width, image.height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", header) + _png_chunk(b"IDAT", bytes(compressed)) + _png_chunk(b"IEND", b"")


def save_png(path: str, image: RenderedImage, transparent: bool = True) -> None:
    with open(path, "wb") as output:
        output.write(encode_png(image, transparent=transparent))

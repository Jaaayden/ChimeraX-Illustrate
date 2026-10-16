"""Independent pure-Python reference implementation of the Illustrate raster pipeline.

This is the list-based renderer that used to live in ``src/render.py`` as the
fallback backend.  ChimeraX always ships NumPy, so the shipped bundle only keeps
the NumPy backend; this slower implementation stays here as a test oracle that
the NumPy backend must match pixel for pixel.
"""

from functools import lru_cache
import math
from typing import List, Sequence, Tuple

from src.render import (
    AtomRecord,
    IllustrationStyle,
    RenderScene,
    RenderedImage,
    ViewSnapshot,
    _center_viewed_coordinates,
    _clamp,
    _contour_thresholds,
    _mat_vec,
    _shadow_offsets,
)


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


def render_python(scene: RenderScene, view: ViewSnapshot, style: IllustrationStyle,
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

    center = _center_viewed_coordinates(scene.atoms, view)
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

    # The shadow neighborhood scales with the output size, as in the NumPy backend.
    shadow_offsets = _shadow_offsets(style) if style.shadows else []

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

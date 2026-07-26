"""ChimeraX-to-Illustrate scene capture adapters.

All ChimeraX objects are read on the UI thread and converted to the immutable
data classes in :mod:`illustrate.render` before rendering starts.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

from .render import AtomRecord, IllustrationStyle, RenderScene, ViewSnapshot


def _as_color(value, default=(1.0, 1.0, 1.0)):
    if value is None:
        return default
    for method_name in ("uint8x4", "rgba", "rgba8"):
        method = getattr(value, method_name, None)
        if callable(method):
            try:
                value = method()
                break
            except Exception:
                pass
    try:
        values = list(value)
    except TypeError:
        return default
    if len(values) < 3:
        return default
    scale = 255.0 if max(float(v) for v in values[:3]) > 1.0 else 1.0
    return tuple(max(0.0, min(1.0, float(v) / scale)) for v in values[:3])


def _model_name(model) -> str:
    value = getattr(model, "id_string", None)
    if value is None:
        value = getattr(model, "name", None)
    if value is None:
        value = getattr(model, "id", "model")
    return str(value)


def _atom_radius(atom) -> float:
    radius = getattr(atom, "radius", None)
    try:
        radius = float(radius)
        if radius > 0.0:
            return radius
    except (TypeError, ValueError):
        pass
    element = getattr(atom, "element", None)
    fallback = getattr(element, "vdw_radius", 1.5)
    try:
        return max(0.0, float(fallback))
    except (TypeError, ValueError):
        return 1.5


def _chain_id(atom) -> str:
    residue = getattr(atom, "residue", None)
    chain = getattr(residue, "chain", None)
    value = getattr(chain, "chain_id", None)
    return str(value if value not in (None, "") else "_")


def _residue_number(atom) -> int:
    residue = getattr(atom, "residue", None)
    value = getattr(residue, "number", 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _matrix_rows(place):
    matrix = getattr(place, "matrix", None)
    if callable(matrix):
        matrix = matrix()
    if matrix is not None:
        try:
            rows = [list(row) for row in matrix]
            if len(rows) >= 3 and len(rows[0]) >= 4:
                return tuple(tuple(float(rows[i][j]) for j in range(4)) for i in range(3))
        except (TypeError, ValueError, IndexError):
            pass
    axes = getattr(place, "axes", None)
    origin = getattr(place, "origin", None)
    try:
        if callable(axes):
            axes = axes()
        if callable(origin):
            origin = origin()
        axes = [list(axis) for axis in axes]
        origin = list(origin)
        if len(axes) == 3 and len(origin) >= 3:
            return (
                (float(axes[0][0]), float(axes[0][1]), float(axes[0][2]), float(origin[0])),
                (float(axes[1][0]), float(axes[1][1]), float(axes[1][2]), float(origin[1])),
                (float(axes[2][0]), float(axes[2][1]), float(axes[2][2]), float(origin[2])),
            )
    except (TypeError, ValueError, IndexError):
        pass
    return ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0))


def _camera_transform(camera):
    place = getattr(camera, "position", None)
    if place is None:
        return ((1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0)), (0.0, 0.0, 0.0)
    inverse = place
    inverse_method = getattr(place, "inverse", None)
    if callable(inverse_method):
        try:
            inverse = inverse_method()
        except Exception:
            inverse = place
    rows = _matrix_rows(inverse)
    # Place maps camera coordinates to scene coordinates.  The inverse maps
    # scene coordinates to camera coordinates; flip camera y for image rows.
    # The renderer's _mat_vec() applies a matrix by columns, while a
    # ChimeraX Place.matrix is a row-wise 3x4 transform.  Transpose the
    # linear part here so the captured scene is transformed as
    # ``inverse_place * scene_point``.  ChimeraX camera y increases upward;
    # image-row y increases downward, hence the sign change on that axis.
    rotation = (
        (rows[0][0], -rows[1][0], rows[2][0]),
        (rows[0][1], -rows[1][1], rows[2][1]),
        (rows[0][2], -rows[1][2], rows[2][2]),
    )
    translation = (rows[0][3], -rows[1][3], rows[2][3])
    return rotation, translation


def _scene_models(session):
    try:
        from chimerax.atomic import AtomicStructure
    except ImportError:
        AtomicStructure = None
    models = getattr(session, "models", None)
    if models is None:
        return []
    listing = getattr(models, "list", None)
    if not callable(listing):
        return []
    if AtomicStructure is None:
        return [
            model for model in listing()
            if hasattr(model, "atoms") and not hasattr(model, "show_atoms")
        ]
    try:
        return listing(type=AtomicStructure)
    except TypeError:
        return [model for model in listing() if isinstance(model, AtomicStructure)]


def _surface_models(session):
    try:
        from chimerax.atomic import MolecularSurface
    except ImportError:
        MolecularSurface = None
    models = getattr(session, "models", None)
    if models is None:
        return []
    listing = getattr(models, "list", None)
    if not callable(listing):
        return []
    if MolecularSurface is None:
        return [
            model for model in listing()
            if hasattr(model, "show_atoms") and hasattr(model, "atoms")
        ]
    try:
        return listing(type=MolecularSurface)
    except TypeError:
        return [model for model in listing() if isinstance(model, MolecularSurface)]


def _model_is_visible(model) -> bool:
    return bool(
        getattr(model, "display", True)
        and getattr(model, "parents_displayed", True)
    )


def _atom_key(atom):
    pointer = getattr(atom, "cpp_pointer", None)
    return pointer if pointer is not None else id(atom)


def _surface_atom_colors(session):
    colors = {}
    for surface in _surface_models(session):
        if not _model_is_visible(surface):
            continue
        shown_atoms = getattr(surface, "show_atoms", None)
        if shown_atoms is None:
            shown_atoms = getattr(surface, "atoms", ())
        color = getattr(surface, "overall_color", None)
        if color is None:
            color = getattr(surface, "color", None)
        color = _as_color(color)
        for atom in shown_atoms:
            colors.setdefault(_atom_key(atom), color)
    return colors


def _atom_is_displayed(atom) -> bool:
    visible = getattr(atom, "visible", None)
    if visible is not None:
        return bool(visible)
    return bool(getattr(atom, "display", True))


def _cartoon_is_displayed(residue) -> bool:
    if residue is None or not getattr(residue, "ribbon_display", False):
        return False
    polymer_type = getattr(residue, "polymer_type", None)
    if polymer_type is None:
        return True
    return polymer_type != getattr(residue, "PT_NONE", 0)


def _atom_is_hydrogen(atom) -> bool:
    element = getattr(atom, "element", None)
    number = getattr(element, "number", None)
    try:
        if number is not None:
            return int(number) == 1
    except (TypeError, ValueError):
        pass
    name = getattr(element, "name", None)
    return str(name).upper() == "H" if name is not None else False


def _atom_scene_coord(atom):
    coord = getattr(atom, "scene_coord", None)
    if coord is None:
        coord = getattr(atom, "coord", None)
    try:
        coord = tuple(float(value) for value in coord)
    except (TypeError, ValueError):
        return None
    return coord if len(coord) == 3 else None


def _representation_color(atom, atom_displayed, surface_color, cartoon_displayed):
    if atom_displayed:
        return _as_color(getattr(atom, "color", None))
    if surface_color is not None:
        return surface_color
    if cartoon_displayed:
        residue = getattr(atom, "residue", None)
        return _as_color(
            getattr(residue, "ribbon_color", None),
            _as_color(getattr(atom, "color", None)),
        )
    return _as_color(getattr(atom, "color", None))


def capture_scene(session, width: int = 800, height: int = 800):
    """Capture atoms represented by visible atoms, cartoons, or surfaces."""

    atoms: List[AtomRecord] = []
    surface_colors = _surface_atom_colors(session)
    for model in _scene_models(session):
        if not _model_is_visible(model):
            continue
        for atom in getattr(model, "atoms", ()):
            atom_displayed = _atom_is_displayed(atom)
            residue = getattr(atom, "residue", None)
            cartoon_displayed = _cartoon_is_displayed(residue)
            surface_color = surface_colors.get(_atom_key(atom))
            if not (atom_displayed or cartoon_displayed or surface_color is not None):
                continue
            if not atom_displayed and _atom_is_hydrogen(atom):
                continue
            coord = _atom_scene_coord(atom)
            if coord is None:
                continue
            atoms.append(AtomRecord(
                coord=coord,
                color=_representation_color(
                    atom, atom_displayed, surface_color, cartoon_displayed
                ),
                radius=_atom_radius(atom),
                subunit="%s:%s" % (_model_name(model), _chain_id(atom)),
                residue=_residue_number(atom),
                atom_name=str(getattr(atom, "name", "")),
            ))

    view = getattr(session, "main_view", None)
    camera = getattr(view, "camera", None)
    if camera is None:
        rotation, translation = ((1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0)), (0.0, 0.0, 0.0)
        scale = 12.0
        projection = "orthographic"
    else:
        rotation, translation = _camera_transform(camera)
        projection = str(getattr(camera, "name", "unknown"))
        center = [0.0, 0.0, 0.0]
        if atoms:
            for atom in atoms:
                for i in range(3):
                    center[i] += atom.coord[i]
            center = [value / len(atoms) for value in center]
        try:
            visible_width = float(camera.view_width(tuple(center)))
            scale = float(width) / visible_width if visible_width > 0.0 else 12.0
        except Exception:
            scale = 12.0

    background = (1.0, 1.0, 1.0)
    if view is not None:
        background = _as_color(getattr(view, "background_color", None), background)
    render_scene = RenderScene(tuple(atoms))
    view_snapshot = ViewSnapshot(
        rotation=rotation,
        translation=translation,
        pixels_per_angstrom=max(0.01, scale),
        auto_center=False,
        projection=projection,
    )
    style = IllustrationStyle(background=background, fog_color=background)
    warnings = []
    if not atoms:
        warnings.append(
            "没有可捕获的原子、cartoon 或 molecular surface"
        )
    if "ortho" not in projection.lower() and projection not in ("unknown", ""):
        warnings.append("当前相机为透视投影；Illustrate 预览使用正交投影")
    return render_scene, view_snapshot, style, "；".join(warnings)

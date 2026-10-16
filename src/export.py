"""Qt-free capture and export helpers.

Both the tool window and the ``illustrate save`` command use these functions,
so exporting works without the graphical interface (for example in
``ChimeraX --nogui`` scripts) and always finishes before the caller returns.
"""

from __future__ import annotations

from typing import Optional, Tuple

from .render import (
    MAX_RENDER_SIZE,
    IllustrationStyle,
    RenderScene,
    ViewSnapshot,
    render_scaled,
    save_png,
)
from .scene import WARNING_NO_ATOMS, WARNING_PERSPECTIVE, capture_scene


DEFAULT_PREVIEW_SIZE = 512
MIN_PREVIEW_SIZE = 64
MAX_PREVIEW_SIZE = 2048
DEFAULT_OUTPUT_WIDTH = 1200
DEFAULT_OUTPUT_HEIGHT = 1200
MIN_OUTPUT_SIZE = 2
MAX_OUTPUT_SIZE = MAX_RENDER_SIZE
# Images with more pixels than this get a memory/time notice before rendering.
LARGE_EXPORT_PIXELS = 36_000_000
# Measured peak memory of the renderer plus PNG writer, per output pixel.
_PEAK_BYTES_PER_PIXEL = 32  # measured 24-34, rounded up

WARNING_TEXT = {
    WARNING_NO_ATOMS: (
        "No visible atoms, cartoons, or molecular surfaces were captured"
    ),
    WARNING_PERSPECTIVE: (
        "Perspective camera detected; Illustrate renders an orthographic view"
    ),
}


class ExportError(ValueError):
    """Raised for an export request that cannot be fulfilled."""


def is_large_export(width: int, height: int) -> bool:
    return width * height > LARGE_EXPORT_PIXELS


def estimated_memory_gb(width: int, height: int) -> float:
    """Rough peak memory, in GiB, for rendering and writing a ``width`` x ``height`` PNG."""

    return width * height * _PEAK_BYTES_PER_PIXEL / float(1 << 30)


def check_output_size(width: int, height: int) -> Optional[str]:
    """Return ``None`` or the message key describing why a size is invalid."""

    if width < MIN_OUTPUT_SIZE or height < MIN_OUTPUT_SIZE:
        return "minimum_size"
    if width > MAX_OUTPUT_SIZE or height > MAX_OUTPUT_SIZE:
        return "maximum_size"
    return None


def render_snapshot_to_png(scene: RenderScene, view: ViewSnapshot,
                           style: IllustrationStyle, capture_width: int,
                           width: int, height: int, path: str,
                           transparent: bool = True) -> str:
    """Render a captured snapshot at the requested size and write a PNG."""

    image = render_scaled(scene, view, style, capture_width, width, height)
    save_png(path, image, transparent=transparent)
    return path


def export_png(session, path: str, transparent: bool = True,
               width: Optional[int] = None, height: Optional[int] = None,
               prefer_atom_colors: bool = False) -> Tuple[str, Tuple[str, ...]]:
    """Capture the current ChimeraX scene and write it as an Illustrate PNG.

    Runs synchronously and returns ``(path, warnings)``.  Raises
    :class:`ExportError` for an empty scene or an invalid size.
    """

    width = int(width or DEFAULT_OUTPUT_WIDTH)
    height = int(height or DEFAULT_OUTPUT_HEIGHT)
    problem = check_output_size(width, height)
    if problem == "minimum_size":
        raise ExportError(
            "PNG dimensions must be at least %d pixels" % MIN_OUTPUT_SIZE
        )
    if problem == "maximum_size":
        raise ExportError(
            "PNG dimensions must not exceed %d pixels" % MAX_OUTPUT_SIZE
        )
    scene, view, style, warnings = capture_scene(
        session, DEFAULT_PREVIEW_SIZE, DEFAULT_PREVIEW_SIZE,
        prefer_atom_colors=prefer_atom_colors,
    )
    if not scene.atoms:
        raise ExportError(WARNING_TEXT[WARNING_NO_ATOMS])
    render_snapshot_to_png(
        scene, view, style, DEFAULT_PREVIEW_SIZE, width, height, path,
        transparent,
    )
    return path, tuple(warnings)

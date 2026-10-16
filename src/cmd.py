"""The public ``illustrate`` ChimeraX command."""

import os

from chimerax.core.commands import (
    BoolArg, CmdDesc, EnumOf, IntArg, StringArg, register,
)
from chimerax.core.errors import UserError

from .export import WARNING_TEXT, ExportError, export_png

ACTIONS = ("show", "open", "capture", "reset", "save")


def register_command():
    desc = CmdDesc(
        optional=[("action", EnumOf(ACTIONS)), ("filename", StringArg)],
        keyword=[
            ("transparent", BoolArg),
            ("width", IntArg),
            ("height", IntArg),
            ("prefer_atom_colors", BoolArg),
        ],
        synopsis="open the Illustrate tool, capture a scene, or export a PNG",
    )
    register("illustrate", desc, illustrate_cmd)


def _find_tool(session):
    """Return the running Illustrate tool, or ``None``."""

    manager = getattr(session, "tools", None)
    if manager is None:
        return None
    for tool in manager.list():
        if (tool.display_name.casefold() == "illustrate"
                or tool.tool_name.casefold() == "illustrate"):
            return tool
    return None


def _get_tool(session):
    """Return the Illustrate tool window, starting it if necessary."""

    if not session.ui.is_gui:
        raise UserError(
            "The Illustrate tool window needs the graphical interface; "
            "use 'illustrate save filename' to export without it"
        )
    tool = _find_tool(session)
    if tool is not None:
        tool.display(True)
        return tool
    matches = session.toolshed.find_bundle_for_tool("Illustrate", prefix_okay=False)
    if len(matches) == 1:
        bundle_info, tool_name = matches[0]
        return bundle_info.start_tool(session, tool_name)
    if len(matches) > 1:
        raise UserError("Multiple installed tools named Illustrate")
    raise UserError("Unable to start the Illustrate tool")


def _save(session, filename, transparent, width, height, prefer_atom_colors):
    """Write a PNG and return only after the file is complete."""

    if not filename:
        raise UserError("illustrate save requires a PNG filename")
    path = os.path.expanduser(filename)
    tool = _find_tool(session)
    try:
        if tool is not None and tool.has_snapshot():
            # Export what the user captured and tuned in the tool window.
            tool.save_image(
                path, transparent=transparent, width=width, height=height,
                wait=True,
            )
            warnings = ()
        else:
            # No snapshot (or no GUI): capture the current scene directly.
            _path, warnings = export_png(
                session, path, transparent=transparent, width=width,
                height=height, prefer_atom_colors=bool(prefer_atom_colors),
            )
    except ExportError as error:
        raise UserError(str(error))
    except OSError as error:
        raise UserError("Unable to write %s: %s" % (path, error))
    for warning in warnings:
        session.logger.warning(WARNING_TEXT.get(warning, warning))
    session.logger.info("Saved Illustrate image to %s" % path)


def illustrate_cmd(session, action=None, filename=None, transparent=True,
                   width=None, height=None, prefer_atom_colors=None):
    action = (action or "show").lower()
    if action == "save":
        _save(session, filename, transparent, width, height, prefer_atom_colors)
        return None
    tool = _get_tool(session)
    if action in ("show", "open"):
        return tool
    if action == "capture":
        if prefer_atom_colors is not None:
            tool.prefer_atom_colors_checkbox.setChecked(prefer_atom_colors)
        if not tool.capture_scene():
            raise UserError(tool.status.text())
        return tool
    if action == "reset":
        tool.clear_scene()
        return tool
    raise UserError("Unknown illustrate action %r" % action)

"""The public ``illustrate`` ChimeraX command."""

from chimerax.core.commands import BoolArg, CmdDesc, IntArg, StringArg, register
from chimerax.core.errors import UserError


def register_command():
    desc = CmdDesc(
        optional=[("action", StringArg), ("filename", StringArg)],
        keyword=[("transparent", BoolArg), ("width", IntArg), ("height", IntArg)],
        synopsis="open the Illustrate tool, capture a scene, or export a PNG",
    )
    register("illustrate", desc, illustrate_cmd)


def _get_tool(session):
    manager = session.tools
    for tool in manager.list():
        if tool.display_name.casefold() == "illustrate" or tool.tool_name.casefold() == "illustrate":
            tool.display(True)
            return tool

    matches = session.toolshed.find_bundle_for_tool("Illustrate", prefix_okay=False)
    if len(matches) == 1:
        bundle_info, tool_name = matches[0]
        return bundle_info.start_tool(session, tool_name)
    if len(matches) > 1:
        raise UserError("Multiple installed tools named Illustrate")
    raise UserError("Unable to start the Illustrate tool")


def illustrate_cmd(session, action=None, filename=None, transparent=True, width=None, height=None):
    action = (action or "show").lower()
    tool = _get_tool(session)
    if action in ("show", "open"):
        return tool
    if action == "capture":
        tool.capture_scene()
        return tool
    if action == "reset":
        tool.clear_scene()
        return tool
    if action == "save":
        if not filename:
            raise UserError("illustrate save requires a PNG filename")
        tool.save_image(filename, transparent=transparent, width=width, height=height)
        return tool
    raise UserError("Unknown illustrate action %r; use show, capture, save, or reset" % action)

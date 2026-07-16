"""ChimeraX bundle entry point for the Illustrate tool."""

try:
    from chimerax.core.toolshed import BundleAPI
except ImportError:  # Allows the pure renderer to be tested outside ChimeraX.
    BundleAPI = object


class _IllustrateBundleAPI(BundleAPI):
    api_version = 1

    @staticmethod
    def register_command(bi, ci, logger):
        if ci.name == "illustrate":
            from .cmd import register_command
            register_command()

    @staticmethod
    def start_tool(session, bi, ti):
        if ti.name == "Illustrate":
            from .tool import IllustrateTool
            return IllustrateTool(session, ti.name)


bundle_api = _IllustrateBundleAPI()

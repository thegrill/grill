from functools import lru_cache
import contextvars
from pxr import Tf
from pxr.Usdviewq.plugin import PluginContainer
from . import spreadsheet

_USDVIEW_SPREADSHEET_EDITOR_KEY = "_usdview_spreadsheet_editor"
_USDVIEW_API = contextvars.ContextVar("_usdviewApi")


# @lru_cache(maxsize=None)
def __getattr__(name):
    if name == _USDVIEW_SPREADSHEET_EDITOR_KEY:
        print("Initialising spreadsheet editor!")
        usdviewApi = _USDVIEW_API.get()
        import importlib
        importlib.reload(spreadsheet)
        editor = spreadsheet.Spreadsheet(parent=usdviewApi.qMainWindow)
        editor.setStage(usdviewApi.stage)
        return editor
    raise AttributeError(f"module {__name__} has no attribute {name}")


def spreadsheetEditor(usdviewApi):
    print("Launching Spreadsheet Editor!")
    ctx = contextvars.copy_context()

    def getEditor():
        _USDVIEW_API.set(usdviewApi)
        return __getattr__(_USDVIEW_SPREADSHEET_EDITOR_KEY)

    editor = ctx.run(getEditor)
    editor.show()


class GrillPluginContainer(PluginContainer):

    def registerPlugins(self, plugRegistry, usdviewApi):
        self._spreadsheetEditor = plugRegistry.registerCommandPlugin(
            "GrillPluginContainer.spreadsheetEditor",
            "Spreadsheet Editor",
            spreadsheetEditor)

    def configureView(self, plugRegistry, plugUIBuilder):
        tutMenu = plugUIBuilder.findOrCreateMenu("Grill")
        tutMenu.addItem(self._spreadsheetEditor)


Tf.Type.Define(GrillPluginContainer)

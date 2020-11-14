from functools import lru_cache
import contextvars
from pxr import Tf
from pxr.Usdviewq.plugin import PluginContainer
from . import spreadsheet as _spreadsheet
from . import description as _description

_USDVIEW_SPREADSHEET_EDITOR_KEY = "_usdview_spreadsheet_editor"
_USDVIEW_PRIM_DESCRIPTION_KEY = "_usdview_prim_description"
_USDVIEW_API = contextvars.ContextVar("_usdviewApi")


# @lru_cache(maxsize=None)
def __getattr__(name):
    if name == _USDVIEW_SPREADSHEET_EDITOR_KEY:
        print("Initialising spreadsheet editor!")
        usdviewApi = _USDVIEW_API.get()
        import importlib
        importlib.reload(_spreadsheet)
        editor = _spreadsheet.Spreadsheet(parent=usdviewApi.qMainWindow)
        editor.setStage(usdviewApi.stage)
        return editor
    elif name == _USDVIEW_PRIM_DESCRIPTION_KEY:
        print("Initialising prim description!")
        usdviewApi = _USDVIEW_API.get()
        import importlib
        importlib.reload(_description)
        widget = _description.PrimDescription(parent=usdviewApi.qMainWindow)

        def primChanged(new_paths, old_paths):
            new_path = next(iter(new_paths), None)
            if not new_path:
                widget.clear()
            else:
                widget.setPrim(usdviewApi.stage.GetPrimAtPath(new_path))

        usdviewApi.dataModel.selection.signalPrimSelectionChanged.connect(primChanged)
        return widget
    raise AttributeError(f"module {__name__} has no attribute {name}")


def spreadsheet(usdviewApi):
    print("Launching Spreadsheet Editor!")
    ctx = contextvars.copy_context()

    def getEditor():
        _USDVIEW_API.set(usdviewApi)
        return __getattr__(_USDVIEW_SPREADSHEET_EDITOR_KEY)

    editor = ctx.run(getEditor)
    editor.show()


def prim_description(usdviewApi):
    print("Launching Prim Description!")
    ctx = contextvars.copy_context()

    def getEditor():
        _USDVIEW_API.set(usdviewApi)
        return __getattr__(_USDVIEW_PRIM_DESCRIPTION_KEY)

    editor = ctx.run(getEditor)
    if usdviewApi.prim:
        editor.setPrim(usdviewApi.prim)
    editor.show()


class GrillPluginContainer(PluginContainer):

    def registerPlugins(self, plugRegistry, usdviewApi):
        self._spreadsheet = plugRegistry.registerCommandPlugin(
            "GrillPluginContainer.spreadsheet",
            "Spreadsheet Editor",
            spreadsheet)

        self._prim_description = plugRegistry.registerCommandPlugin(
            "GrillPluginContainer.prim_description",
            "Prim Description",
            prim_description)

    def configureView(self, plugRegistry, plugUIBuilder):
        grill_menu = plugUIBuilder.findOrCreateMenu("Grill")
        grill_menu.addItem(self._spreadsheet)
        grill_menu.addItem(self._prim_description)


Tf.Type.Define(GrillPluginContainer)

from functools import lru_cache, partial

from pxr import Tf
from pxr.Usdviewq.plugin import PluginContainer

from . import spreadsheet as _spreadsheet
from . import description as _description


@lru_cache(maxsize=None)
def spreadsheet_editor(usdviewApi):
    widget = _spreadsheet.SpreadsheetEditor(parent=usdviewApi.qMainWindow)
    widget.setStage(usdviewApi.stage)
    return widget


@lru_cache(maxsize=None)
def prim_composition(usdviewApi):
    widget = _description.PrimComposition(parent=usdviewApi.qMainWindow)

    def primChanged(new_paths, old_paths):
        new_path = next(iter(new_paths), None)
        widget.setPrim(usdviewApi.stage.GetPrimAtPath(new_path)) if new_path else widget.clear()

    usdviewApi.dataModel.selection.signalPrimSelectionChanged.connect(primChanged)
    if usdviewApi.prim:
        widget.setPrim(usdviewApi.prim)
    return widget


@lru_cache(maxsize=None)
def layer_stack_composition(usdviewApi):
    widget = _description.LayersComposition(parent=usdviewApi.qMainWindow)
    widget.setStage(usdviewApi.stage)
    return widget


class GrillPlugin(PluginContainer):

    def registerPlugins(self, plugRegistry, usdviewApi):
        def show(_launcher, _usdviewAPI):
            return _launcher(_usdviewAPI).show()

        self._menu_items = [
            plugRegistry.registerCommandPlugin(
                f"Grill.{launcher.__qualname__}",
                launcher.__qualname__.replace("_", " ").title(),  # lazy, naming conventions
                partial(show, launcher),
            )
            # contract: every caller here returns a widget to show.
            for launcher in (spreadsheet_editor, prim_composition, layer_stack_composition)
        ]

    def configureView(self, plugRegistry, plugUIBuilder):
        grill_menu = plugUIBuilder.findOrCreateMenu("Grill")
        for item in self._menu_items:
            grill_menu.addItem(item)


Tf.Type.Define(GrillPlugin)

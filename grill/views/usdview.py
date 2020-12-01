from functools import lru_cache

from pxr import Tf
from pxr.Usdviewq.plugin import PluginContainer

from . import spreadsheet as _spreadsheet
from . import description as _description


@lru_cache(maxsize=None)
def spreadsheet_editor(usdviewApi):
    widget = _spreadsheet.SpreadsheetEditor(parent=usdviewApi.qMainWindow)
    widget.setStage(usdviewApi.stage)
    widget.show()


@lru_cache(maxsize=None)
def prim_composition(usdviewApi):
    widget = _description.PrimComposition(parent=usdviewApi.qMainWindow)

    def primChanged(new_paths, old_paths):
        new_path = next(iter(new_paths), None)
        widget.setPrim(usdviewApi.stage.GetPrimAtPath(new_path)) if new_path else widget.clear()

    usdviewApi.dataModel.selection.signalPrimSelectionChanged.connect(primChanged)
    if usdviewApi.prim:
        widget.setPrim(usdviewApi.prim)
    widget.show()


@lru_cache(maxsize=None)
def layer_stack_composition(usdviewApi):
    widget = _description.LayersComposition(parent=usdviewApi.qMainWindow)
    widget.setStage(usdviewApi.stage)
    widget.show()


class GrillPlugin(PluginContainer):

    def registerPlugins(self, plugRegistry, usdviewApi):
        self._menu_items = [
            plugRegistry.registerCommandPlugin(
                f"Grill.{item.__qualname__}",
                item.__qualname__.replace("_", " ").title(),  # lazy, naming conventions
                item
            )
            for item in (spreadsheet_editor, prim_composition, layer_stack_composition)
        ]

    def configureView(self, plugRegistry, plugUIBuilder):
        grill_menu = plugUIBuilder.findOrCreateMenu("Grill")
        for item in self._menu_items:
            grill_menu.addItem(item)


Tf.Type.Define(GrillPlugin)

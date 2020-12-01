from functools import lru_cache

from pxr import Tf
from pxr.Usdviewq.plugin import PluginContainer

from . import spreadsheet as _spreadsheet
from . import description as _description


@lru_cache(maxsize=None)
def spreadsheet_editor(usdviewApi):
    editor = _spreadsheet.SpreadsheetEditor(parent=usdviewApi.qMainWindow)
    editor.setStage(usdviewApi.stage)
    editor.show()


@lru_cache(maxsize=None)
def prim_composition(usdviewApi):
    editor = _description.PrimComposition(parent=usdviewApi.qMainWindow)

    def primChanged(new_paths, old_paths):
        new_path = next(iter(new_paths), None)
        editor.setPrim(usdviewApi.stage.GetPrimAtPath(new_path)) if new_path else editor.clear()

    usdviewApi.dataModel.selection.signalPrimSelectionChanged.connect(primChanged)
    editor.show()


@lru_cache(maxsize=None)
def layer_stack_composition(usdviewApi):
    editor = _description.LayersComposition(parent=usdviewApi.qMainWindow)
    editor.setStage(usdviewApi.stage)
    editor.show()


class GrillPlugin(PluginContainer):

    def registerPlugins(self, plugRegistry, usdviewApi):
        self._spreadsheet = plugRegistry.registerCommandPlugin(
            "Grill.spreadsheet_editor",
            "Spreadsheet Editor",
            spreadsheet_editor)

        self._prim_composition = plugRegistry.registerCommandPlugin(
            "Grill.prim_composition",
            "Prim Composition",
            prim_composition)

        self._layer_stack_composition = plugRegistry.registerCommandPlugin(
            "Grill.layer_stack_composition",
            "Layer Stack Composition",
            layer_stack_composition)

    def configureView(self, plugRegistry, plugUIBuilder):
        grill_menu = plugUIBuilder.findOrCreateMenu("Grill")
        grill_menu.addItem(self._spreadsheet)
        grill_menu.addItem(self._prim_composition)
        grill_menu.addItem(self._layer_stack_composition)


Tf.Type.Define(GrillPlugin)

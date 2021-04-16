# USDView not on pypi yet, so not possible to test this on CI
import types
from functools import lru_cache, partial

from pxr import Tf
from pxr.Usdviewq.plugin import PluginContainer

from PySide2 import QtWidgets

from . import sheets as _sheets
from . import description as _description
from . import create as _create


def _stage_on_widget(widget_creator):
    @lru_cache(maxsize=None)
    def _launcher(usdviewApi):
        widget = widget_creator(parent=usdviewApi.qMainWindow)
        widget.setStage(usdviewApi.stage)
        return widget
    return _launcher


@lru_cache(maxsize=None)
def prim_composition(usdviewApi):
    widget = _description.PrimComposition(parent=usdviewApi.qMainWindow)

    def primChanged(new_paths, __):
        new_path = next(iter(new_paths), None)
        widget.setPrim(usdviewApi.stage.GetPrimAtPath(new_path)) if new_path else widget.clear()

    usdviewApi.dataModel.selection.signalPrimSelectionChanged.connect(primChanged)
    if usdviewApi.prim:
        widget.setPrim(usdviewApi.prim)
    return widget


def save_changes(usdviewApi):
    def show():
        text = "All changes will be saved to disk.\n\nContiue?"
        if QtWidgets.QMessageBox.question(
                usdviewApi.qMainWindow, "Save Changes", text
        ) == QtWidgets.QMessageBox.Yes:
            usdviewApi.stage.Save()
    return types.SimpleNamespace(show=show)


def repository_path(usdviewApi):
    parent = usdviewApi.qMainWindow
    show = partial(_create.CreateAssets._setRepositoryPath, parent)
    return types.SimpleNamespace(show=show)


class GrillPlugin(PluginContainer):

    def registerPlugins(self, plugRegistry, usdviewApi):
        def show(_launcher, _usdviewAPI):
            return _launcher(_usdviewAPI).show()

        def _menu_item(title, _launcher):
            # contract: each of these return an object which show a widget on `show()`
            return plugRegistry.registerCommandPlugin(
                f"Grill.{title.replace(' ', '_')}", title, partial(show, _launcher),
            )

        self._menu_items = [
            _menu_item(title, launcher)
            for (title, launcher) in (
                ("Create Assets", _stage_on_widget(_create.CreateAssets)),
                ("Spreadsheet Editor", _stage_on_widget(_sheets.SpreadsheetEditor)),
                ("Prim Composition", prim_composition),
                ("Layer Stack Composition", _stage_on_widget(_description.LayersComposition)),
                ("Save Changes", save_changes),
            )
        ]

        self._preferences_items = [_menu_item("Repository Path", repository_path)]

    def configureView(self, plugRegistry, plugUIBuilder):
        grill_menu = plugUIBuilder.findOrCreateMenu("👨‍🍳 Grill")
        for item in self._menu_items:
            grill_menu.addItem(item)
        grill_menu.addSeparator()
        preferences = grill_menu.findOrCreateSubmenu("Preferences")
        for item in self._preferences_items:
            preferences.addItem(item)


Tf.Type.Define(GrillPlugin)

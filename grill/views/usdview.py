# USDView not on pypi yet, so not possible to test this on CI
import types
import operator
import contextvars
from functools import lru_cache, partial

from pxr import Tf
from pxr.Usdviewq import plugin, layerStackContextMenu

from PySide2 import QtWidgets

from . import sheets as _sheets, description as _description, create as _create, _core

_usdview_api = contextvars.ContextVar("_usdview_api")  # TODO: is there a better way?
_description._PALETTE.set(0)  # TODO 2: same question


def _stage_on_widget(widget_creator):
    @lru_cache(maxsize=None)
    def _launcher(usdviewApi):
        widget = widget_creator(parent=usdviewApi.qMainWindow)
        widget.setStage(usdviewApi.stage)
        widget.setStyleSheet(_core._USDVIEW_PUSH_BUTTON_STYLE)
        return widget
    return _launcher


def _layer_stack_from_prims(usdviewApi):
    widget = _description.LayerStackComposition(parent=usdviewApi.qMainWindow)
    widget.setStyleSheet(_core._USDVIEW_PUSH_BUTTON_STYLE)
    widget.setPrimPaths(usdviewApi.dataModel.selection.getPrimPaths())
    widget.setStage(usdviewApi.stage)
    return widget


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
        if QtWidgets.QMessageBox.question(
            usdviewApi.qMainWindow, "Save Changes", "All changes will be saved to disk.\n\nContiue?"
        ) == QtWidgets.QMessageBox.Yes:
            usdviewApi.stage.Save()
    return types.SimpleNamespace(show=show)


def repository_path(usdviewApi):
    show = partial(_create.CreateAssets._setRepositoryPath, usdviewApi.qMainWindow)
    return types.SimpleNamespace(show=show)


_original = layerStackContextMenu._GetContextMenuItems


def _extended(item):
    return [  # if it looks like a duck
        GrillContentBrowserLayerMenuItem(item),
    ] + _original(item)


layerStackContextMenu._GetContextMenuItems = _extended


class GrillContentBrowserLayerMenuItem(layerStackContextMenu.LayerStackContextMenuItem):
    def GetText(self):
        return _description._BROWSE_CONTENTS_MENU_TITLE

    def RunCommand(self):
        if self._item and getattr(self._item, 'layer', None):  # USDView allows for single layer selection in composition tab :(
            usdview_api = _usdview_api.get()
            _description._launch_content_browser([self._item.layer], usdview_api.qMainWindow, usdview_api.stage.GetPathResolverContext())


class GrillPlugin(plugin.PluginContainer):

    def registerPlugins(self, plugRegistry, usdviewApi):
        _usdview_api.set(usdviewApi)

        def show(_launcher, _usdviewAPI):
            return _launcher(_usdviewAPI).show()

        def _menu_item(title, _launcher):
            # contract: _launcher() returns an object that shows a widget on `show()`
            return plugRegistry.registerCommandPlugin(
                f"Grill.{title.replace(' ', '_')}", title, partial(show, _launcher),
            )

        self._menu_items = [
            *(_menu_item(title, launcher)
            for (title, launcher) in (
                ("Create Assets", _stage_on_widget(_create.CreateAssets)),
                ("Taxonomy Editor", _stage_on_widget(_create.TaxonomyEditor)),
                ("Spreadsheet Editor", _stage_on_widget(_sheets.SpreadsheetEditor)),
                ("Prim Composition", prim_composition),
            )),
            {"LayerStack Composition": [
                _menu_item("From Current Stage", _stage_on_widget(_description.LayerStackComposition)),
                _menu_item("From Selected Prims", _layer_stack_from_prims),
            ]},
            _menu_item("Save Changes", save_changes),
            operator.methodcaller("addSeparator"),
            {"Preferences": [_menu_item("Repository Path", repository_path)],},
        ]

    def configureView(self, plugRegistry, plugUIBuilder):
        def _populate_menu(menu, items):
            for item in items:
                if isinstance(item, operator.methodcaller):
                    item(menu)
                elif isinstance(item, dict):
                    for child_menu_name, child_items in item.items():
                        child_menu = menu.findOrCreateSubmenu(child_menu_name)
                        _populate_menu(child_menu, child_items)
                else:
                    menu.addItem(item)
        grill_menu = plugUIBuilder.findOrCreateMenu("👨‍🍳 Grill")
        _populate_menu(grill_menu, self._menu_items)


Tf.Type.Define(GrillPlugin)

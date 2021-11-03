# USDView not on pypi yet, so not possible to test this on CI
import types
import operator
import contextvars
from functools import lru_cache, partial

from pxr import UsdGeom, Usd, Sdf, Ar, Tf
from pxr.Usdviewq import plugin, layerStackContextMenu, attributeViewContextMenu

from ._qt import QtWidgets

from . import sheets as _sheets, description as _description, create as _create, _core

_usdview_api = contextvars.ContextVar("_usdview_api")  # TODO: is there a better way?
_description._PALETTE.set(0)  # TODO 2: same question (0 == dark, 1 == light)


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


class GrillContentBrowserLayerMenuItem(layerStackContextMenu.LayerStackContextMenuItem):
    def IsEnabled(self):
        # Layer Stack Tab provides `layerPath`. Composition provides `layer`. Try both.
        return bool(getattr(self._item, 'layer', None) or getattr(self._item, 'layerPath', None))

    def GetText(self):
        return _description._BROWSE_CONTENTS_MENU_TITLE

    def RunCommand(self):
        if self._item:
            usdview_api = _usdview_api.get()
            context = usdview_api.stage.GetPathResolverContext()
            layer = getattr(self._item, 'layer', None)  # USDView allows for single layer selection in composition tab :(
            if not layer:
                layerPath = getattr(self._item, 'layerPath', "")
                # We're protected by the IsEnabled method above, so don't bother checkin layerPath value
                with Ar.ResolverContextBinder(context):
                    layer = Sdf.Layer.FindOrOpen(layerPath)
                    if not layer:  # edge case, is this possible?
                        print(f"Could not find layer from {layerPath}")
                        return
            _description._launch_content_browser([layer], usdview_api.qMainWindow, context)


class GrillAttributeEditorMenuItem(attributeViewContextMenu.AttributeViewContextMenuItem):
    @property
    def _attributes(self):
        return [i for i in self._dataModel.selection.getProps() if isinstance(i, Usd.Attribute)]

    def ShouldDisplay(self):
        return self._role == attributeViewContextMenu.PropertyViewDataRoles.ATTRIBUTE

    def IsEnabled(self):
        return self._item and self._attributes

    def GetText(self):
        return "Edit Value (s)"

    def RunCommand(self):
        attributes = self._attributes
        if attributes:
            editor = _ValueEditor(_usdview_api.get().qMainWindow)
            editor.setAttributes(attributes)
            editor.show()


class _ValueEditor(QtWidgets.QDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        layout = QtWidgets.QFormLayout(self)
        self.setLayout(layout)
        self.setWindowTitle("Experimental Value Editor")

    def setAttributes(self, attributes):
        layout = self.layout()
        supported_primvars = {"displayColor"}
        for attr in attributes:
            primvar = UsdGeom.Primvar(attr)
            if primvar and primvar.GetPrimvarName() in supported_primvars:
                editor = QtWidgets.QFrame()
                editor_layout = QtWidgets.QVBoxLayout()
                editor_layout.addWidget(QtWidgets.QLineEdit())
                color_options = ["faceVarying", "vertex", "constant"]
                # If constant:
                #   Show single color option
                # Else:
                #   Show color range (start, finish) OR Random
                color_options_box = QtWidgets.QComboBox()
                color_options_box.addItems(color_options)
                editor_layout.addWidget(QtWidgets.QColorDialog())
                editor_layout.addWidget(color_options_box)
                editor.setLayout(editor_layout)
                layout.addRow(primvar.GetPrimvarName(), editor)
            elif attr.GetTypeName() == Sdf.ValueTypeNames.Double:
                def update(what, value):
                    what.Set(value)
                editor = QtWidgets.QDoubleSpinBox(self)
                editor.setValue(attr.Get())
                layout.addRow(attr.GetName(), editor)
                editor.valueChanged.connect(partial(update, attr))
            elif attr.GetTypeName() == Sdf.ValueTypeNames.Bool:
                editor = QtWidgets.QCheckBox(self)
                editor.setChecked(attr.Get())
                layout.addRow(attr.GetName(), editor)
                def update(what, *__):
                    what.Set(editor.isChecked())
                editor.stateChanged.connect(partial(update, attr))
            else:
                print(f"Don't know how to edit {attr}")


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


for module, member_name, extender in (
        (layerStackContextMenu, "_GetContextMenuItems", GrillContentBrowserLayerMenuItem),
        # _GetContextMenuItems(item, dataModel) signature is inverse than GrillAttributeEditorMenuItem(dataModel, item)
        (attributeViewContextMenu, "_GetContextMenuItems", lambda *args: GrillAttributeEditorMenuItem(*reversed(args)))
):
    def _extended(_extender, original, *args):
        return [_extender(*args)] + original(*args)  # if it looks like a duck
    setattr(module, member_name, partial(_extended, extender, getattr(module, member_name)))


Tf.Type.Define(GrillPlugin)

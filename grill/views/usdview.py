# USDView not on pypi yet, so not possible to test this on CI
import types
import inspect
import operator
import contextvars
from functools import lru_cache, partial

from pxr import UsdGeom, Usd, Sdf, Ar, Tf
from pxr.Usdviewq import plugin, layerStackContextMenu, attributeViewContextMenu, primContextMenuItems, primContextMenu

import grill.usd as gusd

from ._qt import QtWidgets, QtGui
from . import _core, _attributes, sheets as _sheets, description as _description, create as _create, stats as _stats

_usdview_api = contextvars.ContextVar("_usdview_api")  # TODO: is there a better way?
_description._PALETTE.set(0)  # TODO 2: same question (0 == dark, 1 == light)


def _findOrCreateMenu(parent, title):
    return next((child for child in parent.findChildren(QtWidgets.QMenu) if child.title() == title), None) or parent.addMenu(title)


def _addAction(self, *args, **kwargs):
    if len(args) == 2:
        # primContextMenu.PrimContextMenu calls addAction(menuItem.GetText(), menuItem.RunCommand)
        # This will break as soon as it's called differently, but it's a risk worth to take for now.
        path, method = args
        if inspect.ismethod(method) and isinstance(method.__self__, (_GrillPrimContextMenuItem, GrillAttributeEditorMenuItem)):
            path_segments = path.split("|")
            if len(path_segments) > 2:
                raise RuntimeError(f"Don't know how to handle submenus larger than 2: {path_segments}")
            if len(path_segments) == 2:
                submenu, action_text = path_segments
                child_menu = _findOrCreateMenu(self, submenu)
                if action_text == "...":
                    for text, runner in method.__self__._GetSubCommands():
                        child_menu.addAction(text, runner)
                    return
                return child_menu.addAction(action_text, method)

    return super(type(self), self).addAction(*args, **kwargs)


primContextMenu.PrimContextMenu.addAction = _addAction
attributeViewContextMenu.AttributeViewContextMenu.addAction = _addAction


def _stage_on_widget(widget_creator):
    @lru_cache(maxsize=None)
    def _launcher(usdviewApi):
        widget = widget_creator(parent=usdviewApi.qMainWindow)
        widget.setStage(usdviewApi.stage)
        return widget
    return _launcher


def _layer_stack_from_prims(usdviewApi):
    widget = _description.LayerStackComposition(parent=usdviewApi.qMainWindow)
    widget.setPrimPaths(usdviewApi.dataModel.selection.getPrimPaths())
    widget.setStage(usdviewApi.stage)
    return widget


@lru_cache(maxsize=None)
def prim_composition(usdviewApi):
    widget = _description.PrimComposition(parent=usdviewApi.qMainWindow)

    def primChanged(new_paths, __):
        widget.setPrim(next(map(usdviewApi.stage.GetPrimAtPath, new_paths), None))

    usdviewApi.dataModel.selection.signalPrimSelectionChanged.connect(primChanged)
    if usdviewApi.prim:
        widget.setPrim(usdviewApi.prim)
    return widget


def _connection_viewer(usdviewApi):
    widget = _description._ConnectableAPIViewer(parent=usdviewApi.qMainWindow)

    def primChanged(new_paths, __):
        widget.setPrim(next(map(usdviewApi.stage.GetPrimAtPath, new_paths), None))

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
            # from testing, only entries in the Composition tab without HasSpecs miss "path"
            if path := getattr(self._item, "path", None):
                if isinstance(path, str):
                    path = Sdf.Path(path)
                paths = [path]
            else:
                paths = []
            usdview_api = _usdview_api.get()
            context = usdview_api.stage.GetPathResolverContext()
            if not (layer:= getattr(self._item, 'layer', None)):  # USDView allows for single layer selection in composition tab :(
                layerPath = getattr(self._item, 'layerPath', "")
                # We're protected by the IsEnabled method above, so don't bother checking layerPath value
                with Ar.ResolverContextBinder(context):
                    if not (layer:=Sdf.Layer.FindOrOpen(layerPath)):  # edge case, is this possible?
                        print(f"Could not find layer from {layerPath}")
                        return
            _description._launch_content_browser([layer], usdview_api.qMainWindow, context, paths=paths)


class _GrillPrimContextMenuItem(primContextMenuItems.PrimContextMenuItem):
    """A prim context menu item class that allows special Grill behavior like being added to submenus."""
    _items = []

    def __init_subclass__(cls, **kwargs):
        _GrillPrimContextMenuItem._items.append(cls)


class GrillPrimCompositionMenuItem(_GrillPrimContextMenuItem):
    _widget = _description.PrimComposition
    _subtitle = "Prim Composition"

    def GetText(self):
        return f"Inspect|{self._subtitle}"

    def RunCommand(self):
        usdview_api = _usdview_api.get()
        # The "double pop up" upon showing widgets does not happen on PySide2, only on PySide6
        for prim in self._selectionDataModel.getPrims():
            widget = self._widget(parent=usdview_api.qMainWindow)
            widget.setPrim(prim)
            widget.show()


class GrillLayerStackCompositionMenuItem(GrillPrimCompositionMenuItem):
    _widget = _description.LayerStackComposition
    _subtitle = "LayerStack Composition"

    def RunCommand(self):
        usdview_api = _usdview_api.get()
        stage = usdview_api.stage
        prims = self._selectionDataModel.getPrims()
        widget = self._widget(parent=usdview_api.qMainWindow)
        widget.setPrimPaths(prim.GetPath() for prim in prims)
        widget.setStage(stage)
        widget.show()


class GrillPrimConnectionViewerMenuItem(GrillPrimCompositionMenuItem):
    _widget = _description._ConnectableAPIViewer
    _subtitle = "Connections"


class AllHierarchyTextMenuItem(_GrillPrimContextMenuItem):
    _include_descendants = True
    _subtitle = "All Descendants"
    _predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)

    def GetText(self):
        return f"Copy Hierarchy|{self._subtitle}"

    def RunCommand(self):
        text = gusd._format_prim_hierarchy(self._selectionDataModel.getPrims(), self._include_descendants, self._predicate)
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(text, QtGui.QClipboard.Selection)
        clipboard.setText(text, QtGui.QClipboard.Clipboard)


class ModelHierarchyTextMenuItem(AllHierarchyTextMenuItem):
    _subtitle = "Model Hierarchy"
    _predicate = Usd.PrimIsModel


class SelectedHierarchyTextMenuItem(AllHierarchyTextMenuItem):
    _include_descendants = False
    _subtitle = "Selection Only"


class _GrillAttributeViewContextMenuItem(attributeViewContextMenu.AttributeViewContextMenuItem):
    """A prim context menu item class that allows special Grill behavior like being added to submenus."""
    _items = []

    def __init_subclass__(cls, **kwargs):
        # _GetContextMenuItems(item, dataModel) signature is inverse than AttributeViewContextMenuItem(dataModel, item)
        _GrillAttributeViewContextMenuItem._items.append(lambda *args: cls(*reversed(args)))

    @property
    def _attributes(self):
        return [i for i in self._dataModel.selection.getProps() if isinstance(i, Usd.Attribute)]

    def ShouldDisplay(self):
        return self._role == attributeViewContextMenu.PropertyViewDataRoles.ATTRIBUTE

    def IsEnabled(self):
        return self._item and self._attributes


class GrillAttributeEditorMenuItem(_GrillAttributeViewContextMenuItem):

    def ShouldDisplay(self):
        return (
            super().ShouldDisplay() and
            attr.GetMetadata('allowedTokens') if len(self._attributes) == 1 and (attr := self._attributes[0]).GetTypeName() == Sdf.ValueTypeNames.Token else True
        )

    def GetText(self):
        if (selected := len(self._attributes)) == 1 and self._attributes[0].GetTypeName() in {Sdf.ValueTypeNames.Bool, Sdf.ValueTypeNames.Token}:
            return "Set Value|..."
        return f"Edit Value{'s' if selected > 1 else ''}"

    def RunCommand(self):
        if attributes:=self._attributes:
            editor = _ValueEditor(_usdview_api.get().qMainWindow)
            editor.setAttributes(attributes)
            editor.show()

    def _GetSubCommands(self):
        """Collect value options to provide as menu actions when an attribute of a supported types is selected."""
        attribute, = self._attributes
        type_name = attribute.GetTypeName()
        if type_name == Sdf.ValueTypeNames.Bool:
            return [(str(value), partial(attribute.Set, value)) for value in (True, False)]
        elif type_name == Sdf.ValueTypeNames.Token:
            tokens = attribute.GetMetadata('allowedTokens')
            return [(value, partial(attribute.Set, value)) for value in tokens]


class GrillAttributeClearMenuItem(_GrillAttributeViewContextMenuItem):

    def GetText(self):
        return f"Clear Value{'s' if len(self._attributes) > 1 else ''}"

    def RunCommand(self):
        with Sdf.ChangeBlock():
            for attribute in self._attributes:
                assert attribute.Clear()

    def IsEnabled(self):
        # Usd.Attribute.Clear operates only on specs with an existing authored default value at the current edit target
        try:
            # USD>=24.11
            spec_getter = Usd.EditTarget.GetAttributeSpecForScenePath
        except AttributeError:
            # USD<24.11
            # Usd.EditTarget.GetSpecForScenePath did not work on earlier usd versions. It was fixed in 24.11.
            def spec_getter(edit_target, path):
                return edit_target.GetLayer().GetAttributeAtPath(edit_target.MapToSpecPath(path))

        return super().IsEnabled() and any(
            (spec := spec_getter(attr.GetStage().GetEditTarget(), attr.GetPath())) and spec.default
            for attr in self._attributes
        )


class GrillAttributeBlockMenuItem(_GrillAttributeViewContextMenuItem):

    def GetText(self):
        return f"Block Value{'s' if len(self._attributes) > 1 else ''}"

    def RunCommand(self):
        with Sdf.ChangeBlock():
            for attribute in self._attributes:
                attribute.Block()

    def IsEnabled(self):
        return super().IsEnabled() and any(attr.HasAuthoredValue() for attr in self._attributes)


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
            print(attr)
            type_name = attr.GetTypeName()
            if (primvar:= UsdGeom.Primvar(attr)) and primvar.GetPrimvarName() in supported_primvars:
                editor = _attributes._DisplayColorEditor(primvar)
                layout.addRow(primvar.GetPrimvarName(), editor)
            elif type_name == Sdf.ValueTypeNames.Token:
                tokens = attr.GetMetadata('allowedTokens') or []  # unregistered tokens could return a None value
                def update(what, value):
                    what.Set(value)
                editor = QtWidgets.QComboBox(self)
                editor.addItems(tokens)
                if (current := attr.Get()) in set(tokens):
                    editor.setCurrentText(current)
                elif not tokens:
                    msg = "No 'allowedTokens' registered"
                    editor.addItems([msg])
                    editor.setCurrentText(msg)
                    editor.setEnabled(False)
                layout.addRow(attr.GetName(), editor)
                editor.currentTextChanged.connect(partial(update, attr))
            elif type_name == Sdf.ValueTypeNames.String:
                def update(what, editor):
                    what.Set(editor.text())
                editor = QtWidgets.QLineEdit(self)
                editor.setText(attr.Get() or "")
                layout.addRow(attr.GetName(), editor)
                editor.returnPressed.connect(partial(update, attr, editor))
            elif type_name in {Sdf.ValueTypeNames.Double, Sdf.ValueTypeNames.Float}:
                def update(what, value):
                    what.Set(value)
                editor = QtWidgets.QDoubleSpinBox(self)
                editor.setValue(attr.Get())
                layout.addRow(attr.GetName(), editor)
                editor.valueChanged.connect(partial(update, attr))
            elif type_name == Sdf.ValueTypeNames.Bool:
                editor = QtWidgets.QCheckBox(self)
                editor.setChecked(attr.Get())
                layout.addRow(attr.GetName(), editor)
                def update(ed, what, *__):
                    what.Set(ed.isChecked())
                editor.stateChanged.connect(partial(update, editor, attr))
            else:
                print(f"Don't know how to edit {attr} of type {type_name}")


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

        # create views capabilities are opt-in and depend on grill-names
        creation_menu_items = (
            ("Create Assets", _stage_on_widget(_create.CreateAssets)),
            ("Taxonomy Editor", _stage_on_widget(_create.TaxonomyEditor)),
        ) if _create.cook else ()
        settings_menu_items = (
            operator.methodcaller("addSeparator"),
            {"Preferences": [_menu_item("Repository Path", repository_path)], },
        ) if _create.cook else ()

        self._menu_items = [
            *(_menu_item(title, launcher) for (title, launcher) in (
                *creation_menu_items,
                ("Spreadsheet Editor", _stage_on_widget(_sheets.SpreadsheetEditor)),
                ("Prim Composition", prim_composition),
                ("Connection Viewer", _connection_viewer),
            )),
            {"LayerStack Composition": [
                _menu_item("From Current Stage", _stage_on_widget(_description.LayerStackComposition)),
                _menu_item("From Selected Prims", _layer_stack_from_prims),
            ]},
            operator.methodcaller("addSeparator"),
            *(_menu_item(title, launcher) for title, launcher in (
                ("Stage Stats", _stage_on_widget(_stats.StageStats)),
                ("Save Changes", save_changes),
            )),
            *settings_menu_items,
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


def _extend_menu(_extender, original, *args):
    return [extension(*args) for extension in _extender] + original(*args)  # if it looks like a duck


for module, member_name, extender in (
        (primContextMenuItems, "_GetContextMenuItems", _GrillPrimContextMenuItem._items),
        (layerStackContextMenu, "_GetContextMenuItems", (GrillContentBrowserLayerMenuItem,)),
        (attributeViewContextMenu, "_GetContextMenuItems", _GrillAttributeViewContextMenuItem._items),
):
    setattr(module, member_name, partial(_extend_menu, extender, getattr(module, member_name)))


# We need to do this since primContextMenu imports the function directly, so re-assign with our recently patched one
primContextMenu._GetContextMenuItems = primContextMenuItems._GetContextMenuItems
Tf.Type.Define(GrillPlugin)


def _patch_style(cls):  # while a nicer way comes up
    original = cls.__init__

    def _init_with_usdview_style(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.setStyleSheet(_core._USDVIEW_STYLE)
    cls.__init__ = _init_with_usdview_style


for cls in _description._Tree, _description.LayerStackComposition, _sheets._StageSpreadsheet:
    # Only when in USDView we want to extend the stylesheet of some of the classes tha require them
    # TODO: find a better way to do this
    _patch_style(cls)

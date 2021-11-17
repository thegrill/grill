import hou
import toolutils
from functools import cache, lru_cache, partial

from . import sheets as _sheets, description as _description, create as _create
_description._PALETTE.set(0)  # (0 == dark, 1 == light)


def _stage_on_widget(widget_creator):
    @cache
    def _launcher():
        widget = widget_creator(parent=hou.qt.mainWindow())
        # TODO: Get stage from current node or from current viewport?
        #       Investigate pros & cons and decide.
        viewer = toolutils.sceneViewer()
        stage = viewer.stage()
        if stage:
            widget.setStage(stage)

        return widget

    return _launcher


@lru_cache(maxsize=None)
def _creator(widget_creator):
    widget = _stage_on_widget(widget_creator)()
    def refresh_ui():
        viewer = toolutils.sceneViewer()
        node = viewer.currentNode()
        node.cook(force=True)

    widget.accepted.connect(refresh_ui)
    # widget._applied.connect(refresh_ui)  # TODO: fix, errors with PySide Qt 5.12 (houdini)
    return widget


@cache
def _spreadsheet():
    """This is meant to be run under a solaris desktop in houdini.

    :return:
    """
    widget = _stage_on_widget(_sheets.SpreadsheetEditor)()
    def refresh_ui():
        viewer = toolutils.sceneViewer()
        node = viewer.currentNode()
        node.cook(force=True)

    # https://github.com/nexdatas/selector/blob/b4d6ae92f8887d1bee8bd45dd3cc5777be5ccceb/nxsselector/ElementModel.py#L501
    # https://github.com/pyblish/pyblish-qml/blob/master/pyblish_qml/models.py
    # widget.table.itemChanged.connect(refresh_ui)  # TODO: disabled since new model does not have refresh capabilities yet!
    return widget


def _prim_composition():
    editor = _description.PrimComposition(parent=hou.qt.mainWindow())
    editor._prim = None

    def _updatePrim():
        # find a cheaper way for this?
        viewer = toolutils.sceneViewer()
        stage = viewer.stage()
        if not stage:
            editor.clear()
            editor._prim = None
            return
        selection = viewer.currentSceneGraphSelection()
        prims = tuple(stage.GetPrimAtPath(path) for path in selection)
        prim = next(iter(prims), None)
        if not prim:
            if editor._prim:
                editor.clear()
                editor._prim = None
        else:
            if prim != editor._prim:
                editor.setPrim(prim)
                editor._prim = prim

    hou.ui.addEventLoopCallback(_updatePrim)
    return editor


_create_assets = partial(_creator, _create.CreateAssets)
_taxonomy_editor = partial(_creator, _create.TaxonomyEditor)
_layerstack_composition = _stage_on_widget(_description.LayerStackComposition)

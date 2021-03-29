import hou
import toolutils

from . import sheets as _sheets
from . import description as _description


def spreadsheet():
    """This is meant to be run under a solaris desktop in houdini.

    :return:
    """
    print("Launching Spreadsheet Editor!")
    viewer = toolutils.sceneViewer()
    stage = viewer.stage()
    import importlib
    importlib.reload(_sheets)
    editor = _sheets.SpreadsheetEditor(parent=hou.qt.mainWindow())
    editor.setStage(stage)

    def refresh_ui():
        viewer = toolutils.sceneViewer()
        node = viewer.currentNode()
        node.cook(force=True)

    editor.model.itemChanged.connect(refresh_ui)
    editor.show()


def prim_composition():
    print("Launching Prim Composition!")
    import importlib
    importlib.reload(_description)
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
    editor.show()


def layer_stack_composition():
    print("Launching Layer Stack Composition!")
    import importlib
    importlib.reload(_description)
    editor = _description.LayersComposition(parent=hou.qt.mainWindow())
    viewer = toolutils.sceneViewer()
    stage = viewer.stage()
    editor.setStage(stage)
    editor.show()

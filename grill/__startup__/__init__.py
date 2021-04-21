import os
from pathlib import Path

if "MAYA_PLUG_IN_PATH" in os.environ:
    from maya import cmds


def _install(sitedir):
    if "MAYA_PLUG_IN_PATH" in os.environ:
        # inline imports to speed up non-maya sessions.
        from PySide2 import QtCore
        from functools import partial
        # After trial and error, it looks like waiting for a bit via single shot
        # guarantees that the deferred command will execute, even with 1 millisecond.
        QtCore.QTimer.singleShot(1, lambda: cmds.evalDeferred(partial(_usd_pluginfo, sitedir), lp=True))
        QtCore.QTimer.singleShot(1, lambda: cmds.evalDeferred(_maya, lp=True))
    else:
        _usd_pluginfo(sitedir)


def _usd_pluginfo(sitedir):
    os.environ["PXR_PLUGINPATH_NAME"] = f"{Path(sitedir) / 'grill' / 'resources' / 'plugInfo.json'}{os.pathsep}{os.environ.get('PXR_PLUGINPATH_NAME', '')}"


def _maya():
    print(f"Installing The Grill.")
    from grill.views import maya
    cmds.menu("grill",
        label="👨‍🍳 Grill",
        tearOff=True,
        parent="MayaWindow"
    )
    cmds.menuItem("Spreadsheet Editor", command=lambda *x: maya.spreadsheet())
    cmds.menuItem("Prim Composition", command=lambda *x: maya.prim_composition())
    cmds.menuItem("LayerStack Composition", command=lambda *x: maya.layerstack_composition())
    cmds.polyCube()

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
        QtCore.QTimer.singleShot(1, lambda: cmds.evalDeferred(partial(_usd_pluginfo, sitedir)))
        QtCore.QTimer.singleShot(1, lambda: cmds.evalDeferred(_maya))
    else:
        _usd_pluginfo(sitedir)


def _usd_pluginfo(sitedir):
    os.environ["PXR_PLUGINPATH_NAME"] = f"{Path(sitedir) / 'grill' / 'resources' / 'plugInfo.json'}{os.pathsep}{os.environ.get('PXR_PLUGINPATH_NAME', '')}"


def _maya():
    from grill.views import maya
    maya._create_menu()
    cmds.polyCube()

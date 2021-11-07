from maya import cmds
from PySide2 import QtCore


def install():
    # After trial and error, it looks like waiting for a bit via single shot
    # guarantees that the deferred command will execute, even with 1 millisecond.
    QtCore.QTimer.singleShot(1, lambda: cmds.evalDeferred(_install, lp=True))


def _install():
    if cmds.about(batch=True):
        return  # No GUI, nothing to install
    from ..views import maya
    maya.create_menu()

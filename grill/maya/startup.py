from maya import cmds
from PySide2 import QtCore


def install():
    # After trial and error, it looks like waiting for a bit via single shot
    # guarantees that the deferred command will execute, even with 1 millisecond.
    QtCore.QTimer.singleShot(1, lambda: cmds.evalDeferred(_install, lp=True))


def _install():
    print("Installing The Grill.")
    cmds.menu("grill",
        label="Grill",
        tearOff=True,
        parent="MayaWindow"
    )
    cmds.menuItem("Prim Composition", command=lambda: print("Launching prim comp!"))
    cmds.menuItem("LayerStack Composition", command=lambda: print("Launching LS!"))
    cmds.polyCube()


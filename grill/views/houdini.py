from pprint import pprint

import hou
import toolutils

from . import spreadsheet as _spreadsheet


def spreadsheet():
    """This is meant to be run under a solaris desktop in houdini.

    :return:
    """
    print("Launching Spreadsheet Editor!")
    viewer = toolutils.sceneViewer()
    stage = viewer.stage()
    pprint(dir(viewer))
    pprint([x for x in dir(viewer) if 'stage' in x.lower()])
    pprint(locals())
    import importlib
    importlib.reload(_spreadsheet)
    editor = _spreadsheet.Spreadsheet(parent=hou.qt.mainWindow())
    editor.setStage(stage)
    # at the moment, editing the stage from the viewer does not refresh automatically
    # until I preview back and forth to other nodes.
    # E.g. changing the type of a Sphere to a Cube successfully completes but does
    # not update in the viewport until changing view.
    # I've tried hou.ui.triggerUpdate and viewer.restartRenderer without success :(
    # investiagte more.
    #from PySide2 import QtWidgets
    #refresh = QtWidgets.QPushButton("trigger Update", parent=editor)
    #refresh.clicked.connect(viewer.restartRenderer)
    #refresh.clicked.connect(hou.ui.triggerUpdate)
    #refresh.clicked.connect(viewer.deleteAllMemories)
    #editor.layout().addWidget(refresh)
    editor.show()

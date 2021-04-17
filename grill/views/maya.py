from functools import lru_cache

from PySide2 import QtWidgets
from shiboken2 import wrapInstance

import ufe
import mayaUsd
import maya.OpenMayaUI as omui
import maya.api.OpenMaya as om

from grill.views import description as _description


@lru_cache(maxsize=None)
def maya_main_window():
    mayaMainWindowPtr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(mayaMainWindowPtr), QtWidgets.QWidget)


@lru_cache(maxsize=None)
def _stage_on_widget(widget_creator):
    widget = widget_creator(parent=maya_main_window())
    widget.setStage(usdviewApi.stage)
    return widget


@lru_cache(maxsize=None)
def prim_composition():
    widget = _description.PrimComposition(parent=maya_main_window())

    def selection_changed(*_, **__):
        for item in ufe.GlobalSelection.get():
            print(item.path())
            prim = mayaUsd.ufe.getPrimFromRawItem(item.getRawAddress())
            widget.setPrim(prim)
            break
        else:
            widget.clear()

    om.MEventMessage.addEventCallback("UFESelectionChanged", selection_changed)
    selection_changed()
    return widget



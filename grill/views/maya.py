from functools import lru_cache, partial

from maya import cmds
from PySide2 import QtWidgets
from shiboken2 import wrapInstance

import ufe
import mayaUsd
import maya.OpenMayaUI as omui
import maya.api.OpenMaya as om

from . import description as _description, sheets as _sheets


@lru_cache(maxsize=None)
def maya_main_window():
    return wrapInstance(int(omui.MQtUtil.mainWindow()), QtWidgets.QWidget)


# @lru_cache(maxsize=None)
def _stage_on_widget(widget_creator):
    # TODO: allow for stage selection. For now, use the first found
    widget = widget_creator(parent=maya_main_window())
    usd_proxies = cmds.ls(typ='mayaUsdProxyShape', l=True)
    stage = next((mayaUsd.ufe.getStage(node) for node in usd_proxies), None)
    if stage:
        widget.setStage(stage)
    widget.show()


spreadsheet = partial(_stage_on_widget, _sheets.SpreadsheetEditor)
layerstack_composition = partial(_stage_on_widget, _description.LayersComposition)


# @lru_cache(maxsize=None)
def prim_composition():
    widget = _description.PrimComposition(parent=maya_main_window())

    def selection_changed(*_, **__):
        for item in ufe.GlobalSelection.get():
            prim = mayaUsd.ufe.getPrimFromRawItem(item.getRawAddress())
            if prim.IsValid():
                widget.setPrim(prim)
                break
        else:
            widget.clear()

    om.MEventMessage.addEventCallback("UFESelectionChanged", selection_changed)
    selection_changed()
    widget.show()

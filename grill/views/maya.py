from functools import lru_cache, partial

from maya import cmds
from PySide2 import QtWidgets
from shiboken2 import wrapInstance

import ufe
import mayaUsd
import maya.OpenMayaUI as omui
import maya.api.OpenMaya as om

from . import description as _description, sheets as _sheets, create as _create


@lru_cache(maxsize=None)
def maya_main_window():
    return wrapInstance(int(omui.MQtUtil.mainWindow()), QtWidgets.QWidget)


def _stage_on_widget(widget_creator):
    @lru_cache(maxsize=None)
    def _launcher():
        print(f"Launching {widget_creator}!")
        widget = widget_creator(parent=maya_main_window())
        widget.setStyleSheet(
            # Maya checked buttons style look ugly (all black), so we're adding a very
            # slightly modified USDView stylesheet for the push buttons.
            """
            QPushButton{
                /* gradient background */
                background-color: QLinearGradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 rgb(100, 100, 100), stop: 1 rgb(90, 90, 90));

                /* thin dark round border */
                border-width: 1px;
                border-color: rgb(42, 42, 42);
                border-style: solid;
                border-radius: 3;

                /* give the text enough space */
                padding: 3px;
                padding-right: 10px;
                padding-left: 10px;
            }

            /* Darker gradient when the button is pressed down */
            QPushButton:pressed {
                background-color: QLinearGradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 rgb(50, 50, 50), stop: 1 rgb(60, 60, 60));
            }

            QPushButton:checked {
                background-color: QLinearGradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 rgb(60, 65, 70), stop: 1 rgb(70, 75, 80));
            }

            /* Greyed-out colors when the button is disabled */
            QPushButton:disabled {
                background-color: QLinearGradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 rgb(66, 66, 66), stop: 1 rgb(56, 56, 56));
            }
            """
        )
        usd_proxies = cmds.ls(typ='mayaUsdProxyShape', l=True)
        stage = next((mayaUsd.ufe.getStage(node) for node in usd_proxies), None)
        if stage:
            widget.setStage(stage)
        return widget
    return _launcher


create_assets = _stage_on_widget(_create.CreateAssets)
spreadsheet = _stage_on_widget(_sheets.SpreadsheetEditor)
layerstack_composition = _stage_on_widget(_description.LayersComposition)


@lru_cache(maxsize=None)
def prim_composition():
    print("Launching PRIM COMP!")
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
    return widget


@lru_cache(maxsize=None)
def _create_menu():
    print(f"Creating The Grill menu.")
    cmds.menu("grill", label="👨‍🍳 Grill", tearOff=True, parent="MayaWindow")

    def show(_launcher, *_, **__):
        return _launcher().show()

    for title, launcher in (
            ("Create Assets", create_assets),
            ("Spreadsheet Editor", spreadsheet),
            ("Prim Composition", prim_composition),
            ("LayerStack Composition", layerstack_composition),
    ):
        cmds.menuItem(title, command=partial(show, launcher))

    cmds.polyCube()

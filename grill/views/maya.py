import logging

from functools import cache, partial

from maya import cmds
from ._qt import QtWidgets

if cmds.about(qt=True).startswith("6"):
    from shiboken6 import wrapInstance
else:
    from shiboken2 import wrapInstance

import ufe
import mayaUsd
import maya.OpenMayaUI as omui
import maya.api.OpenMaya as om

from . import description as _description, sheets as _sheets, create as _create, _core, stats as _stats
_description._PALETTE.set(0)  # (0 == dark, 1 == light)

_logger = logging.getLogger(__name__)


@cache
def _main_window():
    return wrapInstance(int(omui.MQtUtil.mainWindow()), QtWidgets.QWidget)


def _stage_on_widget(widget_creator, _cache=True):
    def _launcher():
        widget = widget_creator(parent=_main_window())
        widget.setStyleSheet(
            # Maya checked buttons style look ugly (all black),
            # so re-use the USDView style for push buttons
            _core._USDVIEW_PUSH_BUTTON_STYLE + """
            /* Without this, maya shows larger, pixelated arrows when sorting tables. */
            QHeaderView::down-arrow { top: 1px; width: 13px; height:9px; subcontrol-position: top center;}
            """
        )
        usd_proxies = cmds.ls(typ='mayaUsdProxyShape', l=True)
        stage = next((mayaUsd.ufe.getStage(node) for node in usd_proxies), None)
        if stage:
            widget.setStage(stage)
        return widget
    if _cache:
        _launcher = cache(_launcher)
    return _launcher


@cache
def _prim_composition():
    widget = _description.PrimComposition(parent=_main_window())

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


@cache
def _connections_viewer():
    widget = _description._ConnectableAPIViewer(parent=_main_window())

    def selection_changed(*_, **__):
        for item in ufe.GlobalSelection.get():
            prim = mayaUsd.ufe.getPrimFromRawItem(item.getRawAddress())
            if prim.IsValid():
                widget.setPrim(prim)
                break
        else:
            widget.setPrim(None)

    om.MEventMessage.addEventCallback("UFESelectionChanged", selection_changed)
    selection_changed()
    return widget


@cache
def create_menu():
    _logger.info(f"Creating The Grill menu.")
    menu = cmds.menu("grill", label="👨‍🍳 Grill", tearOff=True, parent="MayaWindow")

    def show(_launcher, *_, **__):
        return _launcher().show()

    creation_menu_items = (
        ("Create Assets", _stage_on_widget(_create.CreateAssets)),
        ("Taxonomy Editor", _stage_on_widget(_create.TaxonomyEditor)),
    ) if _create.cook else ()

    for title, launcher in (
            *creation_menu_items,
            ("Spreadsheet Editor", _stage_on_widget(_sheets.SpreadsheetEditor)),
            ("Prim Composition", _prim_composition),
            ("Connections Viewer", _connections_viewer),
            ("LayerStack Composition", _stage_on_widget(_description.LayerStackComposition)),
            ("Stage Stats", _stage_on_widget(_stats.StageStats, _cache=False)),
    ):
        cmds.menuItem(title, command=partial(show, launcher), parent=menu)

    return menu

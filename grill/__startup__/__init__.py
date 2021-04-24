"""This module helps with startup logic for The Grill.

It might change quickly to be more robust / cleaner, so don't consider this public API.
"""
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


def _install_houdini_menu():
    import json
    import logging
    logger = logging.getLogger(__name__)
    houdini_user_pref_dir = os.getenv('HOUDINI_USER_PREF_DIR')
    if not os.getenv('HOUDINI_USER_PREF_DIR'):
        raise RuntimeError("Can execute only when a houdini environment with HOUDINI_USER_PREF_DIR is available. Aborting.")
    logger.debug(f"Installing houdini preferences to {houdini_user_pref_dir}")
    # 1. Get the source json package for the grill
    from grill.resources import houdini
    hou_resources = Path(houdini.__path__._path[0])
    hou_pkg_src = hou_resources / 'package.json'
    if not hou_pkg_src.is_file():
        raise RuntimeError(f"Aborting without changes. Could not locate expected package file at {hou_pkg_src}. Try re-installing from PyPi.")
    logger.debug(f"hou_pkg_src = {hou_pkg_src}")
    # 2. Update the source data with the new directory location
    with hou_pkg_src.open() as src_obj:
        pkg_obj = json.load(src_obj)
    logger.debug(f"pkg_obj = {pkg_obj}")
    pkg_obj['env'][0]['HOUDINI_MENU_PATH']['value'] = str(hou_resources)
    logger.debug(f"pkg_obj = {pkg_obj}")
    # 3. Save updated data in user preferences
    hou_pkg_tgt = Path(houdini_user_pref_dir) / "packages" / "grill.json"
    hou_pkg_tgt.parent.mkdir(parents=True, exist_ok=True)
    hou_pkg_tgt.write_text(json.dumps(pkg_obj, indent=4))
    logger.info(f"Installed menu on {hou_pkg_tgt}")

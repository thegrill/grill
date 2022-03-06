"""This module aims to provide ease startup of The Grill menus and plugins."""
import os
from pathlib import Path


def install(sitedir):
    # NOTE: if plugInfo provides more plugins other than USDView, it will need to be
    # executed in deferred evaluation in maya and extended on the houdini package.
    _usd_pluginfo(sitedir)

    if "MAYA_PLUG_IN_PATH" in os.environ:  # Quick check for maya plugins
        try:
            from . import maya
        except ImportError:  # Not a proper Maya environment
            pass
        else:
            maya.install()


def _usd_pluginfo(sitedir):
    os.environ["PXR_PLUGINPATH_NAME"] = f"{Path(sitedir) / 'grill' / 'resources' / 'usd' / 'plugInfo.json'}{os.pathsep}{os.environ.get('PXR_PLUGINPATH_NAME', '')}"

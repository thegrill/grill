import os
import json
import logging
from pathlib import Path

from ..resources import houdini

logger = logging.getLogger(__name__)


def install_package():
    """Install The Grill package on the users houdini preferences.

    In the future this might be automatic so no extra user calls should be required.
    """
    logger = logging.getLogger(__name__)
    user_pref_dir = os.getenv('HOUDINI_USER_PREF_DIR')
    if not os.getenv('HOUDINI_USER_PREF_DIR'):
        raise RuntimeError("Can execute only when a houdini environment with HOUDINI_USER_PREF_DIR is available. Aborting.")
    logger.debug(f"Installing houdini preferences to {user_pref_dir}")
    # 1. Get the source json package for the grill
    resources_path = Path(houdini.__path__._path[0])
    pkg_src = resources_path / 'package.json'
    if not pkg_src.is_file():
        raise RuntimeError(f"Aborting without changes. Could not locate expected package file at {pkg_src}. Try re-installing from PyPi.")
    logger.debug(f"pkg_src = {pkg_src}")
    # 2. Update the source data with the new directory location
    pkg_data = json.loads(pkg_src.read_bytes())
    logger.debug(f"pkg_obj = {pkg_data}")
    pkg_data['env'][0]['HOUDINI_MENU_PATH']['value'] = str(resources_path)
    logger.debug(f"pkg_obj = {pkg_data}")
    # 3. Save updated data in user preferences
    pkg_tgt = Path(user_pref_dir) / "packages" / "grill.json"
    pkg_tgt.parent.mkdir(parents=True, exist_ok=True)
    pkg_tgt.write_text(json.dumps(pkg_data, indent=4))
    print(f"Successfully installed package on {pkg_tgt}")

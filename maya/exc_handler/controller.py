# -*- coding: utf-8 -*-
"""
Grill Maya exceptions handler control.
"""
# standard
import os
import sys
import platform
from maya import cmds, utils
# grill
from grill.core.mail import sendBug
from grill.core.exceptions import isGrillException


_ORIG_HOOK = utils.formatGuiException
_INFO_BODY = '''
Scene Info
  Maya Scene: {file_name}
Maya/Python Info
  Maya Version: {maya_version}
  Qt Version: {qt_version}
  Maya64: {maya_x64}
  PyVersion: {python_version}
  PyExe: {python_executable}

Machine Inf
  OS: {os_}
  Node: {node}
  OSRelease: {os_release}
  OSVersion: {os_version}
  Machine: {machine}
  Processor: {processor}
'''

def _handleException(etype, evalue, tb, detail):
    s = utils._formatGuiException(etype, evalue, tb, detail)
    body = [s]
    body.append(_collectInfo())
    sendBug('\n'.join(body))
    lines = [s, 'An unhandled exception occurred.',
             'A report is automatically being sent with details about it.']
    return '\n'.join(lines)


def _collectInfo():
    file_name = cmds.file(q=True, sn=True)
    maya_version = cmds.about(v=True)
    qt_version = cmds.about(qtVersion=True)
    maya_x64 = cmds.about(is64=True)
    python_version = sys.version
    python_executable = sys.executable
    os_ = cmds.about(os=True)
    node = platform.node()
    os_release = platform.release()
    os_version = platform.version()
    machine = platform.machine()
    processor = platform.processor()
    return _INFO_BODY.format(**locals())


def excepthook(etype, evalue, tb, detail=2):
    result = _ORIG_HOOK(etype, evalue, tb, detail)
    if isGrillException(tb):
        result = _handleException(etype, evalue, tb, detail)
    return result

utils.formatGuiException = excepthook

__all__ = ['excepthook']

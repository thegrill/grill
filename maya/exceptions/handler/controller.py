# -*- coding: utf-8 -*-
"""
Grill Maya exceptions handler control.
"""
# standard
import os
import sys
import platform
import threading
from maya import cmds, utils
# grill
from grill.core.mail import sendBug

def _normpath(p):
    return os.path.normpath(os.path.abspath(p))

LIB_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_normpath(__file__)))))
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

def _sendBug(body):
    t = threading.Thread(
        target=sendBug, args=(body,),
        name='send_email_in_background')
    t.start()

def _isGrillException(tb):
    while tb:
        codepath = tb.tb_frame.f_code.co_filename
        if _normpath(codepath).startswith(LIB_DIR):
            return True
        tb = tb.tb_next
    return False

def _handleException(etype, evalue, tb, detail):
    s = utils._formatGuiException(etype, evalue, tb, detail)
    body = [s]
    body.append(_collectInfo())
    _sendBug('\n'.join(body))
    lines = [
        s,
        'An unhandled exception occurred.',
        'An error report was automatically sent with details about the error.']
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
    if _isGrillException(tb):
        result = _handleException(etype, evalue, tb, detail)
    return result

utils.formatGuiException = excepthook

__all__ = ['excepthook']

# -*- coding: utf-8 -*-
"""
This module provides interfaces for reading and writing data.

.. moduleauthor:: Christian López Barrón <christianlb.vfx@outlook.com>

"""
# standard
import json
# package
from . import model

def loadJson(path):
    with open(path) as src:
        return json.load(src)


def dumpJson(path, data):
    with open(path, 'w') as dst:
        json.dump(data, dst)


def getLogFile(loggername):
    return model.LogFile(loggername)

__all__ = ['loadJson', 'dumpJson', 'getLogFile']

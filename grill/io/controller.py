# -*- coding: utf-8 -*-
"""
This module provides interfaces for reading and writing data.

.. moduleauthor:: Christian López Barrón <christianlb.vfx@outlook.com>

"""
# standard
import json
# package
from . import model


def load_json(path):
    with open(path) as src:
        return json.load(src)


def dump_json(path, data):
    with open(path, 'w') as dst:
        json.dump(data, dst)


def get_log_file(loggername):
    return model.LogFile(loggername)

__all__ = ['load_json', 'dump_json', 'get_log_file']

# -*- coding: utf-8 -*-
"""
Grill logging module.
"""
# standard
import os
import logging
# grill
from grill import utils
from grill.core import io
# package
from . import model

_LOGGERS = {}


def _createLogger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(fmt='%(asctime)s %(name)s - %(levelname)s: %(message)s')
    def addHandler(path, log_filter):
        handler = logging.FileHandler(path)
        handler.addFilter(log_filter)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    log_file = io.getLogFile(name)
    log_file.setFilter('stderr')
    addHandler(log_file.path, model.ErrorFilter())
    log_file.setFilter('stdout')
    addHandler(log_file.path, model.OutFilter())
    return logger


def getLogger(name='grill'):
    if name is not 'grill':
        name = 'grill.{}'.format(utils.toCamelCase(name))
    if name not in _LOGGERS:
        _LOGGERS[name] = _createLogger(name)
    return _LOGGERS[name]

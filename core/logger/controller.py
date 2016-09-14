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
    basic_formatter = logging.Formatter(fmt='%(asctime)s %(name)s - %(levelname)s: %(message)s')
    # add stderr handling
    log_file = io.getLogFile(name)
    log_file.setFilter('stderr')
    error = logging.FileHandler(log_file.path)
    error.addFilter(model.ErrorFilter())
    error.setFormatter(basic_formatter)
    logger.addHandler(error)
    # add stdout handling
    log_file.setFilter('stdout')
    out = logging.FileHandler(log_file.path)
    out.addFilter(model.OutFilter())
    out.setFormatter(basic_formatter)
    logger.addHandler(out)
    return logger


def getLogger(name='grill'):
    if name is not 'grill':
        name = 'grill.{}'.format(utils.toCamelCase(name))
    if name not in _LOGGERS:
        _LOGGERS[name] = _createLogger(name)
    return _LOGGERS[name]

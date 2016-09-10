# -*- coding: utf-8 -*-
"""
Grill logging module.
"""
# standard
import os
import logging
from datetime import datetime
# package
from . import model

_LOG_PATH = os.path.join(os.path.expanduser('~'), 'grill', 'log')
_TIME_FORMAT = '%Y%m%d_%H%M%S'
_LOGGERS = {}

if not os.path.exists(_LOG_PATH):
    os.makedirs(_LOG_PATH)


def _createLogger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    log_base_name = '{}_{}'.format(name, datetime.now().strftime(_TIME_FORMAT))
    basic_formatter = logging.Formatter(fmt='%(asctime)s %(name)s - %(levelname)s: %(message)s')
    # add stderr handling
    error = logging.FileHandler(os.path.join(_LOG_PATH, '{}_stderr.txt'.format(log_base_name)))
    error.addFilter(model.ErrorFilter())
    error.setFormatter(basic_formatter)
    logger.addHandler(error)
    # add stdout handling
    out = logging.FileHandler(os.path.join(_LOG_PATH, '{}_stdout.txt'.format(log_base_name)))
    out.addFilter(model.OutFilter())
    out.setFormatter(basic_formatter)
    logger.addHandler(out)
    return logger

def getLogger(name=None):
    name = 'grill.{}'.format(name) if name and name is not 'grill' else 'grill'
    if name not in _LOGGERS:
        _LOGGERS[name] = _createLogger(name)
    return _LOGGERS[name]

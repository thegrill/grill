# -*- coding: utf-8 -*-
"""
Grill logging module.
"""
# standard
import os
import logging
# grill
from grill import utils
from grill import io
# package
from . import model

_LOGGERS = {}


def _create_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(fmt='%(asctime)s %(name)s - %(levelname)s: %(message)s')

    def add_handler(path, log_filter):
        handler = logging.FileHandler(path)
        handler.addFilter(log_filter)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    log_file = io.get_log_file(name)
    log_file.set_filter('stderr')
    add_handler(log_file.path, model.ErrorFilter())
    log_file.set_filter('stdout')
    add_handler(log_file.path, model.OutFilter())
    return logger


def get_logger(name='grill'):
    if name is not 'grill':
        name = 'grill.{}'.format(utils.toCamelCase(name))
    if name not in _LOGGERS:
        _LOGGERS[name] = _create_logger(name)
    return _LOGGERS[name]

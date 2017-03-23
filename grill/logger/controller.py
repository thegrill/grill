# -*- coding: utf-8 -*-
"""
Grill logging module.
"""
import os
import logging
from functools import lru_cache

from . import model


def _create_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(fmt='%(asctime)s %(name)s - %(levelname)s: %(message)s')

    def add_handler(path, log_filter):
        handler = logging.FileHandler(path)
        handler.addFilter(log_filter)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    log_file = model.LogFile.get_default(log_filter=logging.ERROR)
    os.makedirs(log_file.path.parent, exist_ok=True)
    add_handler(log_file.path, model.ErrorFilter())
    log_file.log_filter = logging.INFO
    add_handler(log_file.path, model.OutFilter())
    return logger


@lru_cache(maxsize=None)
def get_logger(name='grill'):
    return _create_logger(name)

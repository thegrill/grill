# -*- coding: utf-8 -*-
"""
Grill logging module.
"""
# standard
from __future__ import annotations

import logging
from pathlib import Path

from naming import NameConfig
from grill.names import DateTimeFile

_LOG_FILE_SUFFIX = 'log'


class ErrorFilter(logging.Filter):
    """
    Pass any message meant for stderr.
    """
    def filter(self, record):
        """
        If the record does is not logging.INFO, return True
        """
        return record.levelno > logging.INFO


class OutFilter(logging.Filter):
    """
    Pass any message meant for stderr.
    """
    def filter(self, record):
        """
        If the record does is logging.INFO, return True
        """
        return record.levelno <= logging.INFO


class LogFile(DateTimeFile):
    """docstring for LogFile"""
    config = dict(
        log_name=r'[\w\.]+',
        log_filter=r'\d+',
    )
    file_config = NameConfig(dict(suffix=_LOG_FILE_SUFFIX))

    @property
    def path(self):
        return Path(r'~/grill').expanduser() / super().name

    @property
    def _defaults(self):
        result = super()._defaults
        result.update(
            log_name='grill',
            log_filter=logging.INFO,
            suffix=_LOG_FILE_SUFFIX,
        )
        return result

# -*- coding: utf-8 -*-
"""
Grill logging module.
"""
# standard
from __future__ import annotations

import logging
from pathlib import Path
from datetime import datetime

from naming import File, NameConfig

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


class LogFile(File):
    """docstring for LogFile"""
    config = dict(
        date=r'\d{4}-(0?[1-9]|1[0-2])-([0-2]?[1-9]|3[01])',
        clock=r'([01]?[0-9]|2[0-4])-[0-5]?[0-9]-[0-5]?[0-9]',
        micosecond=r'\d{1,6}',
        log_name=r'[\w\.]+',
        log_filter=r'\d+',
    )
    file_config = NameConfig(dict(suffix=_LOG_FILE_SUFFIX))

    @property
    def path(self):
        return Path(r'~/grill').expanduser() / super().name

    @classmethod
    def get_default(cls, **kwargs) -> LogFile:
        """Get a new Name object with default values and overrides from **kwargs."""
        now = datetime.now()
        name = cls()
        defaults = dict(
            date=f'{now.year}-{now.month}-{now.day}',
            clock=f'{now.hour}-{now.minute}-{now.second}',
            micosecond=now.microsecond,
            log_name='grill',
            log_filter=logging.INFO,
            suffix=_LOG_FILE_SUFFIX,
        )
        defaults.update(kwargs)
        name.name = name.get_name(**defaults)
        return name


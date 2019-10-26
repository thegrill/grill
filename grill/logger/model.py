# -*- coding: utf-8 -*-
"""
Grill logging module.
"""
# standard
from __future__ import annotations

import typing
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


class TimeFile(File):
    """Time based file names respecting iso standard
    """
    config = dict.fromkeys(
        ('year', 'month', 'day', 'hour', 'minute', 'second', 'microsecond'), r'\d{1,2}'
    )
    config.update(year=r'\d{1,4}', microsecond=r'\d{1,6}')
    join = dict(
        date=('year', 'month', 'day'),
        time=('hour', 'minute', 'second', 'microsecond'),
    )
    join_sep = '-'

    def get_pattern_list(self) -> typing.List[str]:
        return ["date", "time"]

    @property
    def name(self):
        return super().name

    @name.setter
    def name(self, name: str):
        prev_name = self._name
        super(TimeFile, self.__class__).name.fset(self, name)
        # validate with datetime isoformat directly
        if name:
            isodate = f"{int(self.year):04d}-{int(self.month):02d}-{int(self.day):02d}"
            isoclock = f"{int(self.hour):02d}:{int(self.minute):02d}:{int(self.second):02d}.{int(self.microsecond):06d}"
            # if iso validation fails, we fail
            # if we had a previous valid name, revert to it
            try:
                datetime.fromisoformat(f'{isodate}T{isoclock}')
            except ValueError:
                if prev_name:
                    self.name = prev_name
                raise

    @classmethod
    def get_default(cls, **kwargs) -> TimeFile:
        """ Get a new Name object with default values and overrides from **kwargs.

        Note: `join` fields can not be overridden by **kwargs as the atomic fields
              take precedence. To override compounds, pass each individual field:

              >>>
        """
        now = datetime.now()
        name = cls()
        time_field = {'year', 'month', 'day', 'hour', 'minute', 'second', 'microsecond'}
        defaults = dict(
            {f: getattr(now, f) for f in time_field},
            suffix='ext',
        )
        defaults.update(kwargs)
        name.name = name.get_name(**defaults)
        return name

class LogFile(TimeFile):
    """docstring for LogFile"""
    config = dict(
        log_name=r'[\w\.]+',
        log_filter=r'\d+',
    )
    join_sep = '-'
    file_config = NameConfig(dict(suffix=_LOG_FILE_SUFFIX))

    @property
    def path(self):
        return Path(r'~/grill').expanduser() / super().name

    @classmethod
    def get_default(cls, **kwargs) -> LogFile:
        """ Get a new Name object with default values and overrides from **kwargs.

        Note: `join` fields can not be overridden by **kwargs as the atomic fields
              take precedence. To override compounds, pass each individual field:

              >>>
        """
        now = datetime.now()
        name = cls()
        time_field = {'year', 'month', 'day', 'hour', 'minute', 'second', 'microsecond'}
        defaults = dict(
            {f: getattr(now, f) for f in time_field},
            log_name='grill',
            log_filter=logging.INFO,
            suffix=_LOG_FILE_SUFFIX,
        )
        defaults.update(kwargs)
        name.name = name.get_name(**defaults)
        return name

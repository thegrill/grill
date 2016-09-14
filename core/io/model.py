# -*- coding: utf-8 -*-
"""
This module provides the model for reading and writing data.

.. moduleauthor:: Christian López Barrón <christianlb.vfx@outlook.com>

"""
# standard
import os
from datetime import datetime
# grill
from grill.core.names import File


TIME_FORMAT = '%Y%m%d_%H%M%S'


USER_GRILL = os.path.join(os.path.expanduser('~'), 'grill')


class IOFile(File):
    """docstring for IOFile"""
    @property
    def dirname(self):
        return USER_GRILL

    def _getPathPatternList(self):
        pattern = ['dirname']
        return pattern


class DateFile(IOFile):
    """docstring for DateFile"""
    def __init__(self, *args, **kwargs):
        super(DateFile, self).__init__(*args)
        date, time = datetime.now().strftime(TIME_FORMAT).split('_')
        self.setName(self.getName(  date=date, time=time,
                                    pipe='_data', extension='txt', **kwargs))

    def _setValues(self):
        super(DateFile, self)._setValues()
        self._date = '[0-9]+'
        self._time = '[0-9]+'

    def _setPatterns(self):
        super(DateFile, self)._setPatterns()
        self._setPattern('date', 'time')

    def _getPatternList(self):
        return ['_date', '_time']


class LogFile(DateFile):
    """docstring for LogFile"""
    def __init__(self, loggername, **kwargs):
        super(LogFile, self).__init__(loggername=loggername, **kwargs)
        self.setFilter('stdout')

    def _setValues(self):
        super(LogFile, self)._setValues()
        self._loggername = '[a-zA-Z0-9\.]+'

    def _setPatterns(self):
        super(LogFile, self)._setPatterns()
        self._setPattern('loggername')

    @property
    def logdir(self):
        return 'log'

    def _getPatternList(self):
        pattern = ['_loggername']
        pattern.extend(super(LogFile, self)._getPatternList())
        return pattern

    def _getPathPatternList(self):
        pattern = super(LogFile, self)._getPathPatternList()
        pattern.extend(['logdir'])
        return pattern

    def setFilter(self, filter_):
        self.setName(self.getName(pipe='_{}'.format(filter_)))

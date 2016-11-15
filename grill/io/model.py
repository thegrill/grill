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

    def _get_path_pattern_list(self):
        return ['dirname']


class DateFile(IOFile):
    """docstring for DateFile"""
    def __init__(self, *args, **kwargs):
        super(DateFile, self).__init__(*args)
        date, time = datetime.now().strftime(TIME_FORMAT).split('_')
        self.set_name(self.get_name(date=date, time=time,
                                    pipe='_data', extension='txt', **kwargs))

    def _set_values(self):
        super(DateFile, self)._set_values()
        self._date = '[0-9]+'
        self._time = '[0-9]+'

    def _set_patterns(self):
        super(DateFile, self)._set_patterns()
        self._set_pattern('date', 'time')

    def _get_pattern_list(self):
        return ['_date', '_time']


class LogFile(DateFile):
    """docstring for LogFile"""
    def __init__(self, loggername, **kwargs):
        super(LogFile, self).__init__(loggername=loggername, **kwargs)
        self.set_filter('stdout')

    def _set_values(self):
        super(LogFile, self)._set_values()
        self._loggername = '[a-zA-Z0-9\.]+'

    def _set_patterns(self):
        super(LogFile, self)._set_patterns()
        self._set_pattern('loggername')

    @property
    def logdir(self):
        return 'log'

    def _get_pattern_list(self):
        pattern = ['_loggername']
        pattern.extend(super(LogFile, self)._get_pattern_list())
        return pattern

    def _get_path_pattern_list(self):
        pattern = super(LogFile, self)._get_path_pattern_list()
        pattern.extend(['logdir'])
        return pattern

    def set_filter(self, filter_):
        self.set_name(self.get_name(pipe='_{}'.format(filter_)))

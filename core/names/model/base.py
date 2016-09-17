# -*- coding: utf-8 -*-
"""
This module holds the base name model for grill data.

Todo:
    * Write appropriate documentation.
"""
# standard
import re
import abc


def __regex_pattern(pattern_name):
    def getter(self):
        return '(?P<{}>{})'.format(pattern_name, getattr(self, '__{}'.format(pattern_name)))

    def setter(self, value):
        setattr(self, '__{}'.format(pattern_name), value)
    return {'fget': getter, 'fset': setter}


class AbstractBase(object):
    __metaclass__ = abc.ABCMeta
    """docstring for AbstractBase"""
    def __init__(self, name=None):
        super(AbstractBase, self).__init__()
        self._setSeparator()
        self.__setName(name)
        self._setPatterns()
        self._setValues()
        self.__setRegex()
        self.__validate()

    def __validate(self):
        if not self.name:
            return
        self.setName(self.name)

    def __setName(self, name):
        self.name = name

    def _setSeparator(self):
        self._separator = '_'

    @property
    def separator(self):
        return self._separator

    @separator.setter
    def separator(self, value):
        self._separator = value

    @abc.abstractmethod
    def _setValues(self):
        return

    @abc.abstractmethod
    def _getPatternList(self):
        return

    def _getValuesPattern(self):
        return [getattr(self, p) for p in self._getPatternList()]

    def setName(self, name):
        if not self.__regex.match(name):
            msg = 'Can not set invalid name "{}".'.format(name)
            raise NameError(msg)
        self.__setName(name)

    def __setRegex(self):
        self.__regex = re.compile('^{}$'.format(self._getJoinedPattern()))

    def _getJoinedPattern(self):
        return self._separator.join(self._getValuesPattern())

    def getValues(self):
        if not self._values:
            return
        return {k: v for k, v in self._values.iteritems() if not self._filterKV(k, v)}

    def _filterKV(self, k, v):
        if self._filterK(k) or self._filterV(v):
            return True

    def _filterK(self, k):
        return

    def _filterV(self, v):
        return

    @property
    def _values(self):
        try:
            return self.__regex.match(self.name).groupdict()
        except (TypeError, AttributeError):
            pass

    @property
    def nice_name(self):
        return self._getNiceName()

    @abc.abstractmethod
    def _setPatterns(self):
        return

    def getName(self, **values):
        if not values and self.name:
            return self.name
        return self._getNiceName(**values)

    def _getNiceName(self, **values):
        return self._separator.join(self._getTranslatedPatternList('_getPatternList', **values))

    def _getTranslatedPatternList(self, pattern, **values):
        self_values = self._values
        _values = []
        for p in getattr(self, pattern)():
            nice_name = p.replace('_', '')
            if nice_name in values:
                _values.append(str(values[nice_name]))
            elif self_values:
                try:
                    value = str(self_values[nice_name])
                except KeyError:
                    value = getattr(self, p)  # must be a valid property
                _values.append(value)
            else:
                _values.append('[{}]'.format(nice_name))
        return _values

    def _setPattern(self, *patterns):
        for p in patterns:
            string = "self.__class__._{0} = property(**__regex_pattern('{0}'))".format(p)  # please fix this hack
            exec string

    def __getattr__(self, attr):
        try:
            return self._values[attr]
        except (KeyError, TypeError):
            raise AttributeError("{} object has no attribute '{}'".format(self.__class__, attr))


class Name(AbstractBase):
    """docstring for Name"""
    def _setValues(self):
        self._base = '[a-zA-Z0-9]+'

    def _setPatterns(self):
        super(Name, self)._setPatterns()
        self._setPattern('base')

    def _getPatternList(self):
        return ['_base']

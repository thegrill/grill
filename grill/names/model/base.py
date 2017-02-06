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
    """This is the base abstract class for Name objects. All subclasses should inherit from Name and not
    from this one."""
    def __init__(self, name=None):
        super(AbstractBase, self).__init__()
        self.__values = None
        self._set_separator()
        self.__set_name(name)
        self._set_patterns()
        self._set_values()
        self.__set_regex()
        self.__validate()

    def __validate(self):
        if not self.name:
            return
        self.set_name(self.name)

    def __set_name(self, name):
        self.name = name

    def _set_separator(self):
        self._separator = '_'

    @property
    def separator(self):
        """str: The string that acts as a separator of all the fields in the name."""
        return self._separator

    @separator.setter
    def separator(self, value):
        self._separator = value

    @abc.abstractmethod
    def _set_values(self):
        return

    @abc.abstractmethod
    def _get_pattern_list(self):
        return

    def _get_values_pattern(self):
        return [getattr(self, p) for p in self._get_pattern_list()]

    def set_name(self, name):
        match = self.__regex.match(name)
        if not match:
            msg = 'Can not set invalid name "{}".'.format(name)
            raise NameError(msg)
        self.__set_name(name)
        self.__values = match.groupdict()

    def __set_regex(self):
        self.__regex = re.compile('^{}$'.format(self._get_joined_pattern()))

    def _get_joined_pattern(self):
        return self._separator.join(self._get_values_pattern())

    def get_values(self):
        if not self._values:
            return
        return {k: v for k, v in self._values.items() if not self._filter_kv(k, v)}

    def _filter_kv(self, k, v):
        if self._filter_k(k) or self._filter_v(v):
            return True

    def _filter_k(self, k):
        return

    def _filter_v(self, v):
        return

    @property
    def _values(self):
        return self.__values

    @property
    def nice_name(self):
        return self._get_nice_name()

    @abc.abstractmethod
    def _set_patterns(self):
        return

    def get_name(self, **values):
        if not values and self.name:
            return self.name
        return self._get_nice_name(**values)

    def _get_nice_name(self, **values):
        return self._separator.join(self._get_translated_pattern_list('_get_pattern_list', **values))

    def _get_translated_pattern_list(self, pattern, **values):
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

    def _set_pattern(self, *patterns):
        for p in patterns:
            string = "self.__class__._{0} = property(**__regex_pattern('{0}'))".format(p)  # please fix this hack
            exec(string)

    def __getattr__(self, attr):
        try:
            return self._values[attr]
        except (KeyError, TypeError):
            raise AttributeError("{} object has no attribute '{}'".format(self.__class__, attr))


class Name(AbstractBase):
    """docstring for Name"""
    def _set_values(self):
        self._base = '[a-zA-Z0-9]+'

    def _set_patterns(self):
        super(Name, self)._set_patterns()
        self._set_pattern('base')

    def _get_pattern_list(self):
        return ['_base']

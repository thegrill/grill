# -*- coding: utf-8 -*-
"""
Object-oriented names.

This module offers the base classes that represent a name in an object oriented way.
New name objects can be created with minimum effort in a flexible way.

Todo:
    * Write appropriate documentation.
"""
# standard
import re
import abc
import typing


def __regex_pattern(pattern_name: str) -> typing.Dict[str, typing.Callable]:
    def getter(self):
        pattern = getattr(self, rf'__{pattern_name}')
        return rf'(?P<{pattern_name}>{pattern})'

    def setter(self, value):
        setattr(self, rf'__{pattern_name}', value)
    return {'fget': getter, 'fset': setter}


class AbstractBase(object):
    __metaclass__ = abc.ABCMeta
    """This is the base abstract class for Name objects. All subclasses are recommended to inherit
    from Name instead of this one."""
    def __init__(self, name=None, separator='_'):
        super(AbstractBase, self).__init__()
        self.__values = {}
        self._set_separator(separator)
        self._set_patterns()
        self._init_name_core(name)

    def _init_name_core(self, name: str):
        self.__set_name(name)
        self._set_values()
        self.__set_regex()
        self.__validate()

    def _set_separator(self, separator: str):
        self._separator = separator
        self._separator_pattern = rf'\{separator}'

    @property
    def separator(self) -> str:
        """The string that acts as a separator of all the fields in the name."""
        return self._separator

    @separator.setter
    def separator(self, value: str):
        self._set_separator(value)
        name = self.get_name(**self.get_values())
        self._init_name_core(name)

    @abc.abstractmethod
    def _set_patterns(self):
        return

    def _set_pattern(self, *patterns):
        for p in patterns:
            string = rf"self.__class__._{p} = property(**__regex_pattern('{p}'))"  # please fix this hack
            exec(string)

    def __set_name(self, name: str):
        self.name = name

    @abc.abstractmethod
    def _set_values(self):
        """"This is the set values method"""
        return

    def __set_regex(self):
        self.__regex = re.compile(r'^{}$'.format(self._get_joined_pattern()))

    def __validate(self):
        if not self.name:
            return
        self.set_name(self.name)

    def set_name(self, name: str):
        """"This is the set name method"""
        match = self.__regex.match(name)
        if not match:
            msg = rf'Can not set invalid name "{name}".'
            raise NameError(msg)
        self.__set_name(name)
        self.__values.update(match.groupdict())

    @property
    def _values(self) -> typing.Dict[str, str]:
        return self.__values

    @abc.abstractmethod
    def _get_pattern_list(self) -> typing.List[str]:
        return []

    def _get_values_pattern(self) -> typing.List[str]:
        return [getattr(self, p) for p in self._get_pattern_list()]

    def _get_joined_pattern(self) -> str:
        return self._separator_pattern.join(self._get_values_pattern())

    def get_values(self) -> typing.Dict[str, str]:
        return {k: v for k, v in self._values.items() if not self._filter_kv(k, v)}

    def _filter_kv(self, k: str, v) -> bool:
        if self._filter_k(k) or self._filter_v(v):
            return True

    def _filter_k(self, k: str):
        return

    def _filter_v(self, v):
        return

    @property
    def nice_name(self) -> str:
        return self._get_nice_name()

    def _get_nice_name(self, **values) -> str:
        return self._separator.join(self._get_translated_pattern_list('_get_pattern_list', **values))

    def get_name(self, **values) -> str:
        if not values and self.name:
            return self.name
        return self._get_nice_name(**values)

    def _get_translated_pattern_list(self, pattern: str, **values) -> typing.List[str]:
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
                _values.append(rf'[{nice_name}]')
        return _values

    def __getattr__(self, attr):
        try:
            return self._values[attr]
        except (KeyError, TypeError):
            raise AttributeError("{} object has no attribute '{}'".format(self.__class__, attr))


class Name(AbstractBase):
    """docstring for Name"""
    def _set_values(self):
        super(Name, self)._set_values()
        self._base = '[a-zA-Z0-9]+'

    def _set_patterns(self):
        super(Name, self)._set_patterns()
        self._set_pattern('base')

    def _get_pattern_list(self):
        super(Name, self)._get_pattern_list()
        return ['_base']


class EasyName(Name):
    config = None

    def __init__(self, *args, **kwargs):
        if self.config is None:
            self.config = {}
        self.__keys = self.config.keys()
        self.__items = self.config.items()
        super(EasyName, self).__init__(*args, **kwargs)

    def _set_values(self):
        super(EasyName, self)._set_values()
        for k, v in self.__items:
            setattr(self, rf'_{k}', v)

    def _set_patterns(self):
        super(EasyName, self)._set_patterns()
        for k in self.__keys:
            self._set_pattern(k)

    def _get_pattern_list(self):
        result = super(EasyName, self)._get_pattern_list()
        result.extend([rf'_{k}' for k in self.__keys])
        return result

RandomName = type('RandomName', (Name,), dict(name='basename', separator='.'))
RandomEasyName = type('RandomEasyName', (EasyName,), dict(config=dict(extra='[a-zA-Z]')))
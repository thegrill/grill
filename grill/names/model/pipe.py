# -*- coding: utf-8 -*-
"""
The pipe module.
"""
# package
from .base import Name


class Pipe(Name):
    """docstring for Pipe"""

    def _set_values(self):
        super(Pipe, self)._set_values()
        self._version = '\d+'
        self._output = '[a-zA-Z0-9]+'
        self._frame = '\d+'
        self._pipe = rf'([.]{self._version}|{self._separator_pattern}{self._output}([.]{self._frame})?)'

    def _set_patterns(self):
        super(Pipe, self)._set_patterns()
        self._set_pattern('pipe', 'version', 'output', 'frame')

    def _get_joined_pattern(self):
        return rf'{super(Pipe, self)._get_joined_pattern()}{self._pipe}'

    @property
    def pipe_name(self):
        try:
            return rf'{self.nice_name}{self.pipe}'
        except AttributeError:
            return rf'{self.nice_name}{self.separator}[pipe]'

    def _filter_v(self, v):
        return v is None

    def _filter_k(self, k):
        return k == 'pipe'

    def get_name(self, **values):
        if not values and self.name:
            return super(Pipe, self).get_name(**values)
        if 'pipe' in values:
            pipe = values['pipe']
        else:
            if 'version' in values:
                pipe = rf'.{values["version"]}'
            elif 'output' in values or 'frame' in values:
                try:
                    output = values.get('output') or self.output or '[output]'
                except AttributeError:
                    output = '[output]'
                pipe = rf'{self.separator}{output}'
                try:
                    pipe = rf'{pipe}.{values["frame"]}'
                except KeyError:
                    pass
            else:
                suffix = rf'{self.separator}[pipe]'
                pipe = self.pipe or suffix if self.name else suffix
        return rf'{super(Pipe, self).get_name(**values)}{pipe}'

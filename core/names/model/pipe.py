# -*- coding: utf-8 -*-
"""
The pipe module.
"""
# package
from .base import Name


class Pipe(Name):
    """docstring for Pipe"""

    def _setValues(self):
        super(Pipe, self)._setValues()
        self._version = '\d+'
        self._output = '[a-zA-Z0-9]+'
        self._frame = '\d+'
        self._pipe = '([.]{}|_{}([.]{})?)'.format(self._version, self._output, self._frame)

    def _setPatterns(self):
        super(Pipe, self)._setPatterns()
        self._setPattern('pipe', 'version', 'output', 'frame')

    def _getJoinedPattern(self):
        return '{}{}'.format(super(Pipe, self)._getJoinedPattern(), self._pipe)

    @property
    def pipe_name(self):
        try:
            return '{}{}'.format(self.nice_name, self.pipe)
        except AttributeError:
            return '{}_[pipe]'.format(self.nice_name)

    def _filterV(self, v):
        return v is None

    def _filterK(self, k):
        return k == 'pipe'

    def getName(self, **values):
        if not values and self.name:
            return super(Pipe, self).getName(**values)
        if 'pipe' in values:
            pipe = values['pipe']
        else:
            if 'version' in values:
                pipe = '.{}'.format(values['version'])
            elif 'output' in values or 'frame' in values:
                try:
                    output = values.get('output') or self.output or '[output]'
                except AttributeError:
                    output = '[output]'
                pipe = '_{}'.format(output)
                try:
                    pipe = '{}.{}'.format(pipe, values['frame'])
                except KeyError:
                    pass
            else:
                pipe = self.pipe or '_[pipe]' if self.name else '_[pipe]'

        name = '{}{}'.format(super(Pipe, self).getName(**values), pipe)
        return name

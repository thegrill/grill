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
        self._pipe = '([.]{}|_{}([.]{})?)'.format(self._version, self._output, self._frame)

    def _set_patterns(self):
        super(Pipe, self)._set_patterns()
        self._set_pattern('pipe', 'version', 'output', 'frame')

    def _get_joined_pattern(self):
        return '{}{}'.format(super(Pipe, self)._get_joined_pattern(), self._pipe)

    @property
    def pipe_name(self):
        try:
            return '{}{}'.format(self.nice_name, self.pipe)
        except AttributeError:
            return '{}_[pipe]'.format(self.nice_name)

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

        name = '{}{}'.format(super(Pipe, self).get_name(**values), pipe)
        return name

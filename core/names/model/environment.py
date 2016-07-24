# -*- coding: utf-8 -*-
"""
The project module.
"""
# package
from .project import Project


class Environment(Project):
    """docstring for Environment"""
    def _setValues(self):
        super(Environment, self)._setValues()
        self._environment = '[a-z]{3}'
        self._code = '[a-z0-9]+'
        self._project = '{}{}'.format(self._environment, self._code)

    def _setPatterns(self):
        super(Environment, self)._setPatterns()
        self._setPattern('environment', 'code')

    def getName(self, **values):
        if values and 'project' not in values:
            try:
                values.update(project='{}{}'.format(values['environment'], values['code']))
            except KeyError:
                pass
        return super(Environment, self).getName(**values)

    def _getPathPatternList(self):
        return ['code', 'environment', 'workarea']

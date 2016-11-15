# -*- coding: utf-8 -*-
"""
The project module.
"""
# package
from .project import Project


class Environment(Project):
    """docstring for Environment"""
    def _set_values(self):
        super(Environment, self)._set_values()
        self._environment = '[a-z]{3}'
        self._code = '[a-z0-9]+'
        self._project = '{}{}'.format(self._environment, self._code)

    def _set_patterns(self):
        super(Environment, self)._set_patterns()
        self._set_pattern('environment', 'code')

    def get_name(self, **values):
        if values and 'project' not in values:
            try:
                environment = values.get('environment', self.environment)
                code = values.get('code', self.code)
            except AttributeError:
                pass
            else:
                values.update(project='{}{}'.format(environment, code))
        return super(Environment, self).get_name(**values)

    def _get_path_pattern_list(self):
        return ['code', 'environment', 'workarea']

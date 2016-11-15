# -*- coding: utf-8 -*-
"""
The project module.
"""
# package
from .file import File


class Project(File):
    """docstring for Project"""
    def _set_values(self):
        super(Project, self)._set_values()
        self._project = '[a-zA-Z0-9]+'
        self._workarea = '[a-zA-Z0-9]+'

    def _set_patterns(self):
        super(Project, self)._set_patterns()
        self._set_pattern('project', 'workarea')

    def _get_pattern_list(self):
        pattern = ['_project', '_workarea']
        return pattern

    def _get_path_pattern_list(self):
        return ['project', 'workarea']

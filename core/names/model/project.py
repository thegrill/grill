# -*- coding: utf-8 -*-
"""
The project module.
"""
# package
from .file import File


class Project(File):
    """docstring for Project"""
    def _setValues(self):
        super(Project, self)._setValues()
        self._project = '[a-zA-Z0-9]+'
        self._workarea = '[a-zA-Z0-9]+'

    def _setPatterns(self):
        super(Project, self)._setPatterns()
        self._setPattern('project', 'workarea')

    def _getPatternList(self):
        pattern = ['_project', '_workarea']
        return pattern

    def _getPathPatternList(self):
        return ['project', 'workarea']

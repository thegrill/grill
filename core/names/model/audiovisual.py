# -*- coding: utf-8 -*-
"""
The audiovisual module.
"""
# package
from .environment import Environment


class Audiovisual(Environment):
    """docstring for Audiovisual"""

    def _setValues(self):
        super(Audiovisual, self)._setValues()
        self._alias = '[a-zA-Z0-9]+'
        self._stage = '[a-z0-9]+'

    def _setPatterns(self):
        super(Audiovisual, self)._setPatterns()
        self._setPattern('alias', 'stage')

    def _getPatternList(self):
        pattern = super(Audiovisual, self)._getPatternList()
        pattern.extend(['_alias', '_stage'])
        return pattern

    def _getPathPatternList(self):
        pattern = super(Audiovisual, self)._getPathPatternList()
        pattern.extend(['alias', 'stage'])
        return pattern

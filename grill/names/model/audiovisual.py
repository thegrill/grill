# -*- coding: utf-8 -*-
"""
The audiovisual module.
"""
# package
from .environment import Environment


class Audiovisual(Environment):
    """docstring for Audiovisual"""

    def _set_values(self):
        super(Audiovisual, self)._set_values()
        self._alias = '[a-zA-Z0-9]+'
        self._stage = '[a-z0-9]+'

    def _set_patterns(self):
        super(Audiovisual, self)._set_patterns()
        self._set_pattern('alias', 'stage')

    def _get_pattern_list(self):
        pattern = super(Audiovisual, self)._get_pattern_list()
        pattern.extend(['_alias', '_stage'])
        return pattern

    def _get_path_pattern_list(self):
        pattern = super(Audiovisual, self)._get_path_pattern_list()
        pattern.extend(['alias', 'stage'])
        return pattern

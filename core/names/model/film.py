# -*- coding: utf-8 -*-
"""
The film module.
"""
# package
from .audiovisual import Audiovisual

# temporary variable placement
ENV = 'pro'


class Film(Audiovisual):
    """docstring for Film"""

    def _setValues(self):
        super(Film, self)._setValues()
        self._kind = '[a-z]'
        self._group = '[a-z0-9]{3}'
        self._area = '[a-z0-9]+'
        self._workarea = '{}{}{}'.format(self._kind, self._group, self._area)
        self._variant = '[a-zA-Z0-9]+'
        self._partition = '[a-zA-Z0-9]+'
        self._layer = '[a-zA-Z0-9]+'

    def _setPatterns(self):
        super(Film, self)._setPatterns()
        self._setPattern('kind', 'group', 'area', 'variant', 'partition', 'layer')

    def _getPatternList(self):
        pattern = super(Film, self)._getPatternList()
        pattern.extend(['_variant', '_partition', '_layer'])
        return pattern

    def _getPathPatternList(self):
        pattern = super(Film, self)._getPathPatternList()
        wa_i = pattern.index('workarea')
        pattern.remove('alias')
        new_p = pattern[:wa_i]
        new_p.extend(['productionenv', 'kind', 'group', 'alias', 'area'])
        new_p.extend(pattern[wa_i + 1:])
        new_p.extend(['variant'])
        return new_p

    def getName(self, **values):
        if values and 'workarea' not in values:
            try:
                kind = values.get('kind', self.kind)
                group = values.get('group', self.group)
                area = values.get('area', self.area)
            except AttributeError:
                pass
            else:
                values.update(workarea='{}{}{}'.format(kind, group, area))
        return super(Film, self).getName(**values)

    @property
    def productionenv(self):
        return ENV

# -*- coding: utf-8 -*-
"""
Maya names for grill data.
"""
from grill.core.names import Name

class MyAttribute(Name):
    """docstring for MyAttribute"""
    def _setSeparator(self):
        self._separator = ''

    def _setValues(self):
        super(MyAttribute, self)._setValues()
        self._plug = '(in|out)'
        self._attribute = '[a-zA-Z]+'
        self._axis = '[XYZ]?'
        self._index = '\d?'

    def _setPatterns(self):
        super(MyAttribute, self)._setPatterns()
        self._setPattern('plug', 'attribute', 'axis', 'index')

    def _getPatternList(self):
        return ['_plug', '_attribute', '_axis', '_index']

# -*- coding: utf-8 -*-
"""
The file module.
"""
# studio
import os
# package
from .pipe import Pipe


class File(Pipe):
    """docstring for File"""
    def _setValues(self):
        super(File, self)._setValues()
        self._extension = '[.](?P<extension>[a-zA-Z0-9]+)'

    def _getJoinedPattern(self):
        return '{}{}'.format(super(File, self)._getJoinedPattern(), self._extension)

    def getName(self, **values):
        if not values and self.name:
            return super(File, self).getName(**values)
        try:
            extension = values['extension']
        except KeyError:
            try:
                extension = self.extension or '[extension]'
            except AttributeError:
                extension = '[extension]'
        return '{}.{}'.format(super(File, self).getName(**values), extension)

    def _getPathPatternList(self):
        return []

    @property
    def path(self):
        args = self._getTranslatedPatternList('_getPathPatternList')
        args.append(self.getName())
        return os.path.join(*args)

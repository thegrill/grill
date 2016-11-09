# -*- coding: utf-8 -*-
"""
Names testing module.
"""
# standard
import unittest
# package
from . import model


class TestNames(unittest.TestCase):

    def testBase(self):
        name = model.base.Name()
        name.getName()
        self.assertFalse(name.getValues())
        name_str = 'basename'
        name.setName(name_str)
        values = name.getValues()
        assert values['base'] == name_str == name.nice_name == name.name

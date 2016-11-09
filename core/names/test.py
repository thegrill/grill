# -*- coding: utf-8 -*-
"""
Names testing module.
"""
# standard
import unittest
# package
from . import model


class TestNames(unittest.TestCase):

    def testBaseName(self):
        name = model.base.Name()
        name.getName()
        self.assertFalse(name.getValues())
        name_str = 'basename'
        name.setName(name_str)
        values = name.getValues()
        self.assertTrue(values['base'] == name_str == name.nice_name == name.name)


    def testPipe(self):
        name = model.pipe.Pipe()
        name.getName()
        self.assertFalse(name.getValues())
        name_str = 'basename_data'
        name.setName(name_str)
        values = name.getValues()
        self.assertEqual(values['base'], name.nice_name)
        self.assertEqual(values['output'], 'data')
        self.assertEqual(name_str, name.name)
        self.assertEqual(name.getName(pipe='_geo'), 'basename_geo')
        self.assertEqual(name.getName(version=17), 'basename.17')
        name.setName(name.getName(output='cache', frame=101))
        self.assertEqual(name.output, 'cache')
        self.assertEqual(name.frame, '101')

    def testFile(self):
        name = model.file.File()
        name.getName()
        self.assertFalse(name.getValues())
        name_str = 'basename_data.ext'
        name.setName(name_str)
        values = name.getValues()
        self.assertEqual(values['extension'], 'ext')
        self.assertEqual(name_str, name.name)
        self.assertEqual('basename', name.nice_name)
        self.assertEqual('basename_data', name.pipe_name)
        name.setName(name.getName(base='face', output='cache', frame=101, extension='png'))
        self.assertEqual(name.extension, 'png')
        self.assertEqual(name.output, 'cache')
        self.assertEqual(name.frame, '101')
        self.assertEqual(name.base, 'face')

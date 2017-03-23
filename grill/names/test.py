# -*- coding: utf-8 -*-
"""
Names testing module.
"""
# standard
import os
import unittest
# package
from . import model


def _get_environment_kwargs():
    pipe = '_base'
    project = 'flmabc'
    workarea = 'first'
    extension = 'abc'
    return locals()


def _get_audiovisual_kwargs():
    values = _get_environment_kwargs()
    values.update(alias='boy', stage='concept')
    return values


def _get_film_kwargs():
    values = _get_audiovisual_kwargs()
    values.update(workarea='achrgeo', variant='original', partition='master', layer='default')
    return values


class TestNames(unittest.TestCase):

    def test_base_name(self):
        name = model.base.Name()
        name.get_name()
        self.assertFalse(name.get_values())
        name_str = 'basename'
        name.set_name(name_str)
        values = name.get_values()
        self.assertTrue(values['base'] == name_str == name.nice_name == name.name)
        name = model.base.Name('basicname')
        self.assertEqual(name.get_name(), 'basicname')
        self.assertEqual(name.separator, '_')

    def test_pipe(self):
        name = model.pipe.Pipe()
        name.get_name()
        self.assertFalse(name.get_values())
        name_str = 'basename_data'
        name.set_name(name_str)
        values = name.get_values()
        self.assertEqual(values['base'], name.nice_name)
        self.assertEqual(values['output'], 'data')
        self.assertEqual(name_str, name.name)
        self.assertEqual(name.get_name(pipe='_geo'), 'basename_geo')
        self.assertEqual(name.get_name(version=17), 'basename.17')
        name.set_name(name.get_name(output='cache', frame=101))
        self.assertEqual(name.output, 'cache')
        self.assertEqual(name.frame, '101')
        name.separator = '-'
        self.assertEqual(name.separator, '-')
        self.assertEqual(name.get_name(), 'basename-cache.101')
        with self.assertRaises(NameError):
            name.set_name('basename_geo.17')
        name.separator = '.'
        self.assertEqual(name.separator, '.')
        self.assertEqual(name.get_name(), 'basename.cache.101')

    def test_file(self):
        name = model.file.File()
        name.get_name()
        self.assertFalse(name.get_values())
        name_str = 'basename_data.ext'
        name.set_name(name_str)
        values = name.get_values()
        self.assertEqual(values['extension'], 'ext')
        self.assertEqual(name._get_path_pattern_list(), [])
        self.assertEqual(name_str, name.name)
        self.assertEqual('basename', name.nice_name)
        self.assertEqual('basename_data', name.pipe_name)
        name.set_name(name.get_name(base='face', output='cache', frame=101, extension='png'))
        self.assertEqual(name.extension, 'png')
        self.assertEqual(name.output, 'cache')
        self.assertEqual(name.frame, '101')
        self.assertEqual(name.base, 'face')

    def test_project(self):
        name = model.project.Project()
        name.set_name(name.get_name(**_get_environment_kwargs()))
        self.assertEqual(name.nice_name, 'flmabc_first')
        self.assertEqual(str(name.path), os.path.join('flmabc', 'first', 'flmabc_first_base.abc'))

    def test_environment(self):
        name = model.environment.Environment()
        name.set_name(name.get_name(**_get_environment_kwargs()))
        self.assertEqual(name.environment, 'flm')
        name.set_name(name.get_name(environment='gme'))
        self.assertEqual(name.environment, 'gme')
        self.assertEqual(name.code, 'abc')
        self.assertEqual(str(name.path), os.path.join('abc', 'gme', 'first', 'gmeabc_first_base.abc'))
        name = model.environment.Environment()
        self.assertEqual(name.get_name(frame=5), '[project]_[workarea]_[output].5.[extension]')
        self.assertEqual(name.pipe_name, '[project]_[workarea]_[pipe]')
        self.assertEqual(name.get_name(extension='ext'), '[project]_[workarea]_[pipe].ext')

    def test_audiovisual(self):
        name = model.Audiovisual()
        self.assertFalse(name.get_values())
        name.set_name(name.get_name(**_get_audiovisual_kwargs()))
        for k, v in name.get_values().items():
            self.assertIsInstance(v, str)
        self.assertEqual(str(name.path), os.path.join('abc', 'flm', 'first', 'boy', 'concept',
                                                 'flmabc_first_boy_concept_base.abc'))

    def test_film(self):
        name = model.Film()
        self.assertEqual(name.get_name(kind='set'), name.get_name())
        name.set_name(name.get_name(**_get_film_kwargs()))
        name.set_name(name.get_name(area='model'))
        self.assertEqual(name.workarea, 'achrmodel')
        self.assertEqual(str(name.path), os.path.join('abc', 'flm', 'pro', 'a', 'chr',
                                                 'boy', 'model', 'concept', 'original',
                                                 'flmabc_achrmodel_boy_concept_original_master_default_base.abc'))
        name.separator = '-'
        self.assertEqual(name.separator, '-')
        self.assertEqual(name.get_name(), 'flmabc-achrmodel-boy-concept-original-master-default-base.abc')
        name.separator = '.'
        self.assertEqual(name.separator, '.')
        self.assertEqual(name.get_name(), 'flmabc.achrmodel.boy.concept.original.master.default.base.abc')
        name.separator = ' '
        name.set_name(name.get_name(area='rig'))
        self.assertEqual(name.workarea, 'achrrig')
        self.assertEqual(name.separator, ' ')
        self.assertEqual(name.get_name(), 'flmabc achrrig boy concept original master default base.abc')
        name.separator = r'/ '
        self.assertEqual(name.separator, r'/ ')
        self.assertEqual(name.get_name(), r'flmabc/ achrrig/ boy/ concept/ original/ master/ default/ base.abc')
        print(name.full_path)
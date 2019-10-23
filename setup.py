#!/usr/bin/env python

from setuptools import setup, find_packages

VERSION = '0.7.0'

setup(
    name='grill',
    version=VERSION,
    packages=find_packages(),
    description='Pipeline and data flow tools for (but not limited to) audiovisual projects, with DCC support.',
    author='Christian Lopez Barron',
    author_email='christianlb.vfx@outlook.com',
    url='https://github.com/thegrill/grill',
    download_url=f'https://github.com/thegrill/grill/releases/tag/{VERSION}',
    classifiers=['Programming Language :: Python :: 3.7'],
    extras_require={'docs': ['sphinx_autodoc_typehints']}
)

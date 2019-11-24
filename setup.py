#!/usr/bin/env python

from setuptools import setup, find_namespace_packages

VERSION = '0.7.3'

setup(
    name='grill',
    version=VERSION,
    packages=find_namespace_packages(
        exclude=("*.tests", "*.tests.*", "tests.*", "tests", "*.docs", "*.docs.*", "docs.*", "docs")
    ),
    description='Pipeline and data flow tools for (but not limited to) audiovisual projects, with DCC support.',
    author='Christian Lopez Barron',
    author_email='christianlb.vfx@outlook.com',
    url='https://github.com/thegrill/grill',
    download_url=f'https://github.com/thegrill/grill/releases/tag/{VERSION}',
    classifiers=[
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
    install_requires=['grill-names'],
    extras_require={'docs': ['sphinx_autodoc_typehints']}
)

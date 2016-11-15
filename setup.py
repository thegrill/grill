#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name='grill',
    version='0.5.1.2',
    packages=find_packages(),
    description='Pipeline and data flow tools for (but not limited to) audiovisual projects, with DCC support.',
    author='Christian Lopez Barron',
    author_email='christianlb.vfx@outlook.com',
    url='https://github.com/chrizzFTD/grill',
    download_url='https://github.com/chrizzFTD/grill/releases/tag/0.5.1.2',
    classifiers=[],
    package_data={
        "grill": ["core/*.py"]
    }
)

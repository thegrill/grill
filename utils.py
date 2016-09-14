# -*- coding: utf-8 -*-
"""
Base utilities.
"""
#standard
import re


def toUnderscores(string):
    parts = re.findall('[A-Z]?[a-z]+', string)
    for i, p in enumerate(parts):
        parts[i] = p.lower()
    return '_'.join(parts)

def toCamelCase(string):
    parts = re.findall('([a-zA-Z0-9]+)', string)
    for i, p in enumerate(parts[1:], start=1):
        parts[i] = '{}{}'.format(p[0].upper(), p[1:])
    return ''.join(parts)

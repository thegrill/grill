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

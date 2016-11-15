# -*- coding: utf-8 -*-
"""
Grill exceptions controller module.
"""
# standard
import os


def _normpath(p):
    return os.path.normpath(os.path.abspath(p))


LIB_DIR = os.path.dirname(os.path.dirname(_normpath(__file__)))


def is_grill_exception(tb):
    while tb:
        codepath = tb.tb_frame.f_code.co_filename
        if _normpath(codepath).startswith(LIB_DIR):
            return True
        tb = tb.tb_next

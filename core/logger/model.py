# -*- coding: utf-8 -*-
"""
Grill logging module.
"""
# standard
import logging


class ErrorFilter(logging.Filter):
    """
    Pass any message meant for stderr.
    """
    def filter(self, record):
        """
        If the record does is not logging.INFO, return True
        """
        return record.levelno != logging.INFO


class OutFilter(logging.Filter):
    """
    Pass any message meant for stderr.
    """
    def filter(self, record):
        """
        If the record does is logging.INFO, return True
        """
        return record.levelno == logging.INFO

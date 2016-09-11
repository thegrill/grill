# -*- coding: utf-8 -*-
"""
Grill logging module.
"""
# grill
from grill.core.logger import LOGGER
# package
from . import model

def sendBug(body, subject='Bug Report'):
    LOGGER.info('Sending mail with bug report.')
    mailer = model.BugsMail(subject, body)
    mailer.send()

__all__ = ['sendBug']
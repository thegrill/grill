# -*- coding: utf-8 -*-
"""
Grill logging module.
"""
# grill
from grill.core.logger import LOGGER
# standard
import smtplib
import threading
from email.mime.text import MIMEText

class Mailer(object):
    """docstring for Mailer"""
    def __init__(self, sender, password, receiver, subject, body):
        super(Mailer, self).__init__()
        self._sender = sender
        self._password = password
        self.receiver = receiver
        self.subject = subject
        self.body = body

    @property
    def sender(self):
        return self._sender

    @property
    def password(self):
        return self._password

    @property
    def receiver(self):
        return self._receiver

    @receiver.setter
    def receiver(self, value):
        self._receiver = value

    @property
    def subject(self):
        return self._subject

    @subject.setter
    def subject(self, value):
        self._subject = value

    @property
    def body(self):
        return self._body

    @body.setter
    def body(self, value):
        self._body = value

    def _send(self, *email_server_args):
        msg = MIMEText(self.body)
        msg['To'] = self.receiver
        msg['From'] = self.sender
        msg['Subject'] = self.subject
        server = smtplib.SMTP(*email_server_args)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(self.sender, self.password)
        try:
            server.sendmail(msg['From'], msg['To'], msg.as_string())
            LOGGER.info('Mail successfully sent.')
        except:
            LOGGER.error('Mail failed to send.')
            raise
        finally:
            server.quit()

    def send(self, *args, **kwargs):
        t = threading.Thread(
            target=self._send, args=args, kwargs=kwargs,
            name='send_email_in_background')
        t.start()


class GMail(Mailer):
    def send(self):
        super(GMail, self).send('smtp.gmail.com', 587)


class BugsMail(GMail):
    def __init__(self, *args, **kwargs):
        super(BugsMail, self).__init__('sender', 'password', 'receiver', *args, **kwargs)

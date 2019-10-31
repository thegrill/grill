import unittest
from grill.logger import model


class TestLogger(unittest.TestCase):

    def test_root_logger(self):
        from grill.logger import LOG
        LOG.info("Info message")

    def test_module_logger(self):
        from grill.logger import get_logger
        logger = get_logger(__name__)
        logger.info("Testing inner module")

    def test_default(self):
        l = model.LogFile.get_default(year=1999, day=1)
        self.assertEqual(l.year, '1999')

        with self.assertRaises(ValueError):
            l.month = 13  # invalid month 13

        for m in range(1, 13):
            l.month = m

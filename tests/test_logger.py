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
        l = model.LogFile.get_default(year=1999)
        self.assertEqual(l.year, '1999')

        with self.assertRaises(ValueError):
            # invalid year 0
            l.month = 0

        with self.assertRaises(ValueError):
            # max year 9999
            l.month = 12345

        for y in range(1, 1000):
            l.year = y
            self.assertEqual(l.year, str(y))

        with self.assertRaises(ValueError):
            # invalid month 13
            l.month = 13

        for m in range(1,13):
            l.month = m

        with self.assertRaises(ValueError):
            # invalid month 0
            l.month = 0

        with self.assertRaises(ValueError):
            # invalid month 13
            l.day = 0

        for m in range(1,32):
            l.day = m

        with self.assertRaises(ValueError):
            # invalid day 32
            l.day = 32
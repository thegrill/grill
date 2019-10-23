import unittest


class TestLogger(unittest.TestCase):

    def test_root_logger(self):
        from grill.logger import LOG
        LOG.info("Info message")

    def test_module_logger(self):
        from grill.logger import get_logger
        logger = get_logger(__name__)
        logger.info("Testing inner module")

import unittest

from grill.logger.model import TimeFile


class TestTimeFile(unittest.TestCase):
    def test_something(self):
        tf = TimeFile.get_default()
        # try valid iso value:
        tf.year = 1997
        name = tf.year
        with self.assertRaises(ValueError):
            # invalid iso year
            tf.year = 0

        # verify we keep previous name after failure
        self.assertEqual(tf.name, name)


if __name__ == '__main__':
    unittest.main()

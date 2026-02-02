import logging
import unittest

from autopkg_wrapper.utils.logging import setup_logger


class TestSetupLogger(unittest.TestCase):
    def test_setup_logger_debug_sets_debug_level(self):
        root = logging.getLogger()
        old_handlers = list(root.handlers)
        try:
            # Reset handlers so basicConfig applies in this test process.
            for h in list(root.handlers):
                root.removeHandler(h)

            setup_logger(debug=True)
            self.assertEqual(root.getEffectiveLevel(), logging.DEBUG)
        finally:
            for h in list(root.handlers):
                root.removeHandler(h)
            for h in old_handlers:
                root.addHandler(h)


if __name__ == "__main__":
    unittest.main()

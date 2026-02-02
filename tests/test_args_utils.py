import os
import tempfile
import unittest
from unittest.mock import patch

from autopkg_wrapper.utils import args as args_utils


class TestArgsUtils(unittest.TestCase):
    def test_validate_bool(self):
        self.assertTrue(args_utils.validate_bool(True))
        self.assertFalse(args_utils.validate_bool(False))

        self.assertFalse(args_utils.validate_bool("0"))
        self.assertFalse(args_utils.validate_bool("false"))
        self.assertFalse(args_utils.validate_bool("No"))
        self.assertFalse(args_utils.validate_bool("F"))

        self.assertTrue(args_utils.validate_bool("1"))
        self.assertTrue(args_utils.validate_bool("true"))
        self.assertTrue(args_utils.validate_bool("YES"))
        self.assertTrue(args_utils.validate_bool("t"))

    def test_validate_file_and_directory(self):
        with tempfile.TemporaryDirectory() as td:
            # directory
            self.assertEqual(
                args_utils.validate_directory(td).as_posix(),
                os.path.realpath(td),
            )

            # file
            fp = os.path.join(td, "example.txt")
            with open(fp, "w", encoding="utf-8") as f:
                f.write("hi")
            self.assertEqual(
                args_utils.validate_file(fp).as_posix(),
                os.path.realpath(fp),
            )

    def test_find_github_token_prefers_github_token(self):
        with patch.dict(
            os.environ, {"GITHUB_TOKEN": "aaa", "GH_TOKEN": "bbb"}, clear=True
        ):
            self.assertEqual(args_utils.find_github_token(), "aaa")

    def test_find_github_token_falls_back_to_gh_token(self):
        with patch.dict(os.environ, {"GH_TOKEN": "bbb"}, clear=True):
            self.assertEqual(args_utils.find_github_token(), "bbb")

    def test_setup_args_reads_processing_order_env_var(self):
        # Note: argparse default comes through as a string when provided via env var.
        with patch.dict(
            os.environ,
            {"AW_RECIPE_PROCESSING_ORDER": "upload,self_service"},
            clear=True,
        ):
            with patch("sys.argv", ["autopkg_wrapper"]):
                parsed = args_utils.setup_args()
        self.assertEqual(parsed.recipe_processing_order, "upload,self_service")


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
from unittest.mock import patch

from autopkg_wrapper.utils import args as args_utils


class TestArgsUtils:
    def test_validate_bool(self):
        assert args_utils.validate_bool(True) is True
        assert args_utils.validate_bool(False) is False

        assert args_utils.validate_bool("0") is False
        assert args_utils.validate_bool("false") is False
        assert args_utils.validate_bool("No") is False
        assert args_utils.validate_bool("F") is False

        assert args_utils.validate_bool("1") is True
        assert args_utils.validate_bool("true") is True
        assert args_utils.validate_bool("YES") is True
        assert args_utils.validate_bool("t") is True

    def test_validate_file_and_directory(self):
        with tempfile.TemporaryDirectory() as td:
            # directory
            assert args_utils.validate_directory(td).as_posix() == os.path.realpath(td)

            # file
            fp = os.path.join(td, "example.txt")
            with open(fp, "w", encoding="utf-8") as f:
                f.write("hi")
            assert args_utils.validate_file(fp).as_posix() == os.path.realpath(fp)

    def test_find_github_token_prefers_github_token(self):
        with patch.dict(
            os.environ, {"GITHUB_TOKEN": "aaa", "GH_TOKEN": "bbb"}, clear=True
        ):
            assert args_utils.find_github_token() == "aaa"

    def test_find_github_token_falls_back_to_gh_token(self):
        with patch.dict(os.environ, {"GH_TOKEN": "bbb"}, clear=True):
            assert args_utils.find_github_token() == "bbb"

    def test_setup_args_reads_processing_order_env_var(self):
        # Note: argparse default comes through as a string when provided via env var.
        with (
            patch.dict(
                os.environ,
                {"AW_RECIPE_PROCESSING_ORDER": "upload,self_service"},
                clear=True,
            ),
            patch("sys.argv", ["autopkg_wrapper"]),
        ):
            parsed = args_utils.setup_args()
        assert parsed.recipe_processing_order == "upload,self_service"

    def test_setup_args_reads_autopkg_bin_env_var(self):
        with (
            patch.dict(os.environ, {"AW_AUTOPKG_BIN": "/opt/bin/autopkg"}, clear=True),
            patch("sys.argv", ["autopkg_wrapper"]),
        ):
            parsed = args_utils.setup_args()
        assert parsed.autopkg_bin == "/opt/bin/autopkg"

    def test_setup_args_cli_autopkg_bin_overrides_env_var(self):
        with (
            patch.dict(os.environ, {"AW_AUTOPKG_BIN": "/opt/bin/autopkg"}, clear=True),
            patch(
                "sys.argv",
                ["autopkg_wrapper", "--autopkg-bin", "/custom/autopkg"],
            ),
        ):
            parsed = args_utils.setup_args()
        assert parsed.autopkg_bin == "/custom/autopkg"

"""Tests for environment variable handling with blank strings."""

import os
from unittest.mock import patch

from autopkg_wrapper.utils.args import getenv_with_default, setup_args


class TestGetenvWithDefault:
    """Test getenv_with_default helper function."""

    def test_returns_value_when_set(self):
        """Test that actual values are returned."""
        with patch.dict(os.environ, {"TEST_VAR": "actual_value"}):
            result = getenv_with_default("TEST_VAR", "default")
            assert result == "actual_value"

    def test_returns_default_when_unset(self):
        """Test that default is returned when variable is unset."""
        with patch.dict(os.environ, {}, clear=True):
            result = getenv_with_default("TEST_VAR", "default")
            assert result == "default"

    def test_returns_default_when_blank(self):
        """Test that default is returned when variable is blank string."""
        with patch.dict(os.environ, {"TEST_VAR": ""}):
            result = getenv_with_default("TEST_VAR", "default")
            assert result == "default"

    def test_handles_none_default(self):
        """Test that None can be used as default."""
        with patch.dict(os.environ, {"TEST_VAR": ""}):
            result = getenv_with_default("TEST_VAR", None)
            assert result is None


class TestArgsWithBlankEnvVars:
    """Test that argument parsing handles blank env vars correctly."""

    def test_blank_autopkg_bin_uses_default(self):
        """Test that blank AW_AUTOPKG_BIN uses default."""
        with (
            patch.dict(os.environ, {"AW_AUTOPKG_BIN": ""}, clear=False),
            patch("sys.argv", ["autopkg_wrapper", "--recipes", "test.recipe"]),
        ):
            args = setup_args()
            assert args.autopkg_bin == "/usr/local/bin/autopkg"

    def test_blank_concurrency_uses_default(self):
        """Test that blank AW_CONCURRENCY uses default."""
        with (
            patch.dict(os.environ, {"AW_CONCURRENCY": ""}, clear=False),
            patch("sys.argv", ["autopkg_wrapper", "--recipes", "test.recipe"]),
        ):
            args = setup_args()
            assert args.concurrency == 10

    def test_blank_reports_extract_dir_uses_default(self):
        """Test that blank AW_REPORTS_EXTRACT_DIR uses default."""
        with (
            patch.dict(os.environ, {"AW_REPORTS_EXTRACT_DIR": ""}, clear=False),
            patch("sys.argv", ["autopkg_wrapper", "--recipes", "test.recipe"]),
        ):
            args = setup_args()
            assert args.reports_extract_dir == "autopkg_reports_summary/reports"

    def test_blank_reports_out_dir_uses_default(self):
        """Test that blank AW_REPORTS_OUT_DIR uses default."""
        with (
            patch.dict(os.environ, {"AW_REPORTS_OUT_DIR": ""}, clear=False),
            patch("sys.argv", ["autopkg_wrapper", "--recipes", "test.recipe"]),
        ):
            args = setup_args()
            assert args.reports_out_dir == "autopkg_reports_summary/summary"

    def test_set_autopkg_bin_overrides_default(self):
        """Test that non-blank AW_AUTOPKG_BIN overrides default."""
        with (
            patch.dict(
                os.environ, {"AW_AUTOPKG_BIN": "/custom/path/autopkg"}, clear=False
            ),
            patch("sys.argv", ["autopkg_wrapper", "--recipes", "test.recipe"]),
        ):
            args = setup_args()
            assert args.autopkg_bin == "/custom/path/autopkg"

    def test_set_concurrency_overrides_default(self):
        """Test that non-blank AW_CONCURRENCY overrides default."""
        with (
            patch.dict(os.environ, {"AW_CONCURRENCY": "5"}, clear=False),
            patch("sys.argv", ["autopkg_wrapper", "--recipes", "test.recipe"]),
        ):
            args = setup_args()
            assert args.concurrency == 5

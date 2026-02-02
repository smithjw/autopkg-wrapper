import tempfile
import unittest
from pathlib import Path as RealPath
from types import SimpleNamespace
from unittest.mock import patch

from autopkg_wrapper.autopkg_wrapper import Recipe


class TestAutopkgCommands(unittest.TestCase):
    def test_verify_trust_info_uses_autopkg_bin_and_sets_verified_true(self):
        r = Recipe("Foo.download")
        args = SimpleNamespace(
            debug=False, autopkg_prefs=None, autopkg_bin="/custom/autopkg"
        )

        with patch("autopkg_wrapper.autopkg_wrapper.subprocess.run") as run:
            run.return_value = SimpleNamespace(returncode=0, stderr="", stdout="")
            ok = r.verify_trust_info(args)

        self.assertTrue(ok)
        called_cmd = run.call_args.args[0]
        self.assertEqual(called_cmd[0], "/custom/autopkg")
        self.assertEqual(called_cmd[1], "verify-trust-info")
        self.assertEqual(called_cmd[2], "Foo.download")

    def test_verify_trust_info_failure_sets_message(self):
        r = Recipe("Foo.download")
        args = SimpleNamespace(
            debug=True, autopkg_prefs=None, autopkg_bin="/usr/local/bin/autopkg"
        )

        with patch("autopkg_wrapper.autopkg_wrapper.subprocess.run") as run:
            run.return_value = SimpleNamespace(
                returncode=1, stderr="bad trust", stdout=""
            )
            ok = r.verify_trust_info(args)

        self.assertFalse(ok)
        self.assertEqual(r.results["message"], "bad trust")

    def test_update_trust_info_uses_autopkg_bin(self):
        r = Recipe("Foo.download")
        args = SimpleNamespace(autopkg_prefs=None, autopkg_bin="/custom/autopkg")

        with patch("autopkg_wrapper.autopkg_wrapper.subprocess.check_call") as cc:
            r.update_trust_info(args)

        called_cmd = cc.call_args.args[0]
        self.assertEqual(called_cmd[0], "/custom/autopkg")
        self.assertEqual(called_cmd[1], "update-trust-info")
        self.assertEqual(called_cmd[2], "Foo.download")

    def test_run_uses_autopkg_bin_and_report_plist(self):
        r = Recipe("Foo.download")
        args = SimpleNamespace(
            debug=False,
            autopkg_prefs=None,
            autopkg_bin="/custom/autopkg",
        )

        with tempfile.TemporaryDirectory() as td:

            def fake_path(arg):
                if arg == "/private/tmp/autopkg":
                    return RealPath(td)
                return RealPath(arg)

            with patch("autopkg_wrapper.autopkg_wrapper.Path", side_effect=fake_path):
                with patch("autopkg_wrapper.autopkg_wrapper.subprocess.run") as run:
                    run.return_value = SimpleNamespace(
                        returncode=0, stderr="", stdout=""
                    )
                    with patch.object(
                        r,
                        "_parse_report",
                        return_value={"imported": [], "failed": []},
                    ):
                        r.verified = True
                        r.run(args)

        called_cmd = run.call_args.args[0]
        self.assertEqual(called_cmd[0], "/custom/autopkg")
        self.assertEqual(called_cmd[1], "run")
        self.assertIn("--report-plist", called_cmd)


if __name__ == "__main__":
    unittest.main()

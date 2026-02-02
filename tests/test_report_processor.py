import os
import plistlib
import tempfile
import unittest

from autopkg_wrapper.utils import report_processor as rp


class TestReportProcessor(unittest.TestCase):
    def test_infer_recipe_name_from_filename(self):
        self.assertEqual(
            rp._infer_recipe_name_from_filename("/tmp/Foo-2026-02-02T01-02-03.plist"),
            "Foo",
        )
        self.assertEqual(rp._infer_recipe_name_from_filename("/tmp/Foo.plist"), "Foo")
        self.assertEqual(
            rp._infer_recipe_name_from_filename("/tmp/Foo-bar.plist"), "Foo-bar"
        )

    def test_find_report_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "nested", "autopkg_report-123"))
            dirs = rp.find_report_dirs(td)
            self.assertEqual(dirs, [os.path.join(td, "nested", "autopkg_report-123")])

        with tempfile.TemporaryDirectory() as td:
            # no autopkg_report-* dirs, but has files -> treat base as report dir
            with open(os.path.join(td, "x.plist"), "wb") as f:
                f.write(b"x")
            dirs = rp.find_report_dirs(td)
            self.assertEqual(dirs, [td])

    def test_parse_text_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "out.txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write("Uploaded Foo version 1.2.3\n")
                f.write("Policy created: Install Foo\n")
                f.write("ERROR: Something broke\n")

            data = rp.parse_text_file(p)

        self.assertEqual(data["uploads"][0]["name"], "Foo")
        self.assertEqual(data["uploads"][0]["version"], "1.2.3")
        self.assertEqual(data["policies"][0]["name"], "Install Foo")
        self.assertEqual(data["policies"][0]["action"], "created")
        self.assertIn("Something broke", data["errors"][0])

    def test_parse_plist_file_extracts_upload_rows_and_errors(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "Foo-2026-02-02T01-02-03.plist")
            plist = {
                "failures": [
                    {
                        "message": "Trust verification failed",
                        "recipe": "Foo.upload.jamf",
                    }
                ],
                "summary_results": {
                    "jamfpackageuploader_summary_result": {
                        "data_rows": [
                            {
                                "name": "Foo",
                                "version": "1.2.3",
                                "pkg_name": "Foo.pkg",
                                "pkg_path": "/Users/me/Library/AutoPkg/Cache/com.github.autopkg/Foo/cache/ABC123/some.pkg",
                            }
                        ]
                    }
                },
            }
            with open(p, "wb") as f:
                plistlib.dump(plist, f)

            data = rp.parse_plist_file(p)

        self.assertEqual(data["uploads"][0]["name"], "Foo")
        self.assertEqual(data["uploads"][0]["version"], "1.2.3")
        self.assertEqual(data["upload_rows"][0]["recipe_name"], "Foo")
        self.assertEqual(data["upload_rows"][0]["recipe_identifier"], "ABC123")
        self.assertEqual(data["error_rows"][0]["error_type"], "trust")

    def test_aggregate_reports_end_to_end(self):
        with tempfile.TemporaryDirectory() as td:
            repdir = os.path.join(td, "autopkg_report-123")
            os.makedirs(repdir)

            # Minimal plist report
            p = os.path.join(repdir, "Foo-2026-02-02T01-02-03.plist")
            plist = {
                "failures": [],
                "summary_results": {
                    "jamfpackageuploader_summary_result": {
                        "data_rows": [
                            {
                                "name": "Foo",
                                "version": "1.2.3",
                                "pkg_name": "Foo.pkg",
                                "pkg_path": "/Users/me/Library/AutoPkg/Cache/com.github.autopkg/Foo/cache/ABC123/some.pkg",
                            }
                        ]
                    }
                },
            }
            with open(p, "wb") as f:
                plistlib.dump(plist, f)

            # A text report alongside it
            t = os.path.join(repdir, "out.txt")
            with open(t, "w", encoding="utf-8") as f:
                f.write("Uploaded Bar version 9.9.9\n")

            summary = rp.aggregate_reports(td)

        self.assertGreaterEqual(summary["recipes"], 1)
        self.assertTrue(any(u.get("name") == "Foo" for u in summary["uploads"]))
        self.assertTrue(any(u.get("name") == "Bar" for u in summary["uploads"]))


if __name__ == "__main__":
    unittest.main()

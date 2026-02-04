import os
import plistlib
import sys
import tempfile

from autopkg_wrapper.utils import report_processor as rp


class TestReportProcessor:
    def test_infer_recipe_identifier_from_filename(self):
        assert (
            rp._infer_recipe_identifier_from_filename(
                "/tmp/Foo-2026-02-02T01-02-03.plist"
            )
            == "Foo"
        )
        assert (
            rp._infer_recipe_identifier_from_filename(
                "/tmp/Foo.upload.jamf-2026-02-02T01-02-03.plist"
            )
            == "Foo.upload.jamf"
        )
        assert rp._infer_recipe_identifier_from_filename("/tmp/Foo.plist") == "Foo"
        assert (
            rp._infer_recipe_identifier_from_filename("/tmp/Foo-bar.plist") == "Foo-bar"
        )
        assert (
            rp._infer_recipe_identifier_from_filename(
                "/tmp/Foo.upload.jamf.recipe.plist"
            )
            == "Foo.upload.jamf"
        )
        assert (
            rp._infer_recipe_identifier_from_filename(
                "/tmp/Foo.upload.jamf.recipe.yaml.plist"
            )
            == "Foo.upload.jamf"
        )

    def test_find_report_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "nested", "autopkg_report-123"))
            dirs = rp.find_report_dirs(td)
            assert dirs == [os.path.join(td, "nested", "autopkg_report-123")]

        with tempfile.TemporaryDirectory() as td:
            # no autopkg_report-* dirs, but has files -> treat base as report dir
            with open(os.path.join(td, "x.plist"), "wb") as f:
                f.write(b"x")
            dirs = rp.find_report_dirs(td)
            assert dirs == [td]

    def test_parse_text_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "out.txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write("Uploaded Foo version 1.2.3\n")
                f.write("Policy created: Install Foo\n")
                f.write("ERROR: Something broke\n")

            data = rp.parse_text_file(p)

        assert data["uploads"][0]["name"] == "Foo"
        assert data["uploads"][0]["version"] == "1.2.3"
        assert data["policies"][0]["name"] == "Install Foo"
        assert data["policies"][0]["action"] == "created"
        assert "Something broke" in data["errors"][0]

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

        assert data["uploads"][0]["name"] == "Foo"
        assert data["uploads"][0]["version"] == "1.2.3"
        assert data["upload_rows"][0]["recipe_name"] == "Foo"
        assert data["upload_rows"][0]["recipe_identifier"] == "Foo"
        assert data["error_rows"][0]["error_type"] == "trust"

    def test_parse_plist_file_extracts_policy_rows(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "Node-2026-02-02T01-02-03.plist")
            plist = {
                "failures": [],
                "summary_results": {
                    "jamfpolicyuploader_summary_result": {
                        "data_rows": [
                            {
                                "policy": "EPZ - node (autopkg)",
                                "template": "/path/to/template.xml",
                            }
                        ]
                    }
                },
            }
            with open(p, "wb") as f:
                plistlib.dump(plist, f)

            data = rp.parse_plist_file(p)

        assert data["policy_rows"][0]["policy"] == "EPZ - node (autopkg)"
        assert data["policy_rows"][0]["recipe_name"] == "Node"

    def test_parse_plist_file_resolves_recipe_link(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "Foo-2026-02-02T01-02-03.plist")
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

            data = rp.parse_plist_file(
                p, recipe_link_map={"Foo.upload.jamf": "https://example.com"}
            )

        assert data["upload_rows"][0]["recipe_name"] == "Foo.upload.jamf"
        assert data["upload_rows"][0]["recipe_url"] == "https://example.com"

    def test_build_pkg_map_handles_result_wrappers(self, monkeypatch):
        class FakePackage:
            def __init__(self, name, pid):
                self.packageName = name
                self.id = pid

        class FakePackages:
            def __init__(self, items):
                self.results = items

        class FakeProApi:
            def get_packages_v1(self):
                return FakePackages([FakePackage("Foo.pkg", 55)])

        class FakeClient:
            def __init__(self, *_args, **_kwargs):
                self.pro_api = FakeProApi()

        class FakeCreds:
            def __init__(self, *_args, **_kwargs):
                pass

        class FakeSdk:
            ApiClientCredentialsProvider = FakeCreds
            JamfProClient = FakeClient

        monkeypatch.setitem(sys.modules, "jamf_pro_sdk", FakeSdk)

        pkg_map = rp.build_pkg_map("https://example.test", "id", "secret", errors=[])

        assert (
            pkg_map["Foo.pkg"]
            == "https://example.test/view/settings/computer-management/packages/55"
        )

    def test_build_policy_map_requires_classic_request(self, monkeypatch):
        class FakeProApi:
            pass

        class FakeClient:
            def __init__(self, *_args, **_kwargs):
                self.pro_api = FakeProApi()

        class FakeCreds:
            def __init__(self, *_args, **_kwargs):
                pass

        class FakeSdk:
            ApiClientCredentialsProvider = FakeCreds
            JamfProClient = FakeClient

        monkeypatch.setitem(sys.modules, "jamf_pro_sdk", FakeSdk)
        errors: list[str] = []

        policy_map = rp.build_policy_map(
            "https://example.test", "id", "secret", errors=errors
        )

        assert policy_map == {}
        assert any("classic API request" in msg for msg in errors)

    def test_coerce_jamf_items_handles_none(self):
        assert rp._coerce_jamf_items(None) == []

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

        assert summary["recipes"] >= 1
        assert any(u.get("name") == "Foo" for u in summary["uploads"])
        assert any(u.get("name") == "Bar" for u in summary["uploads"])

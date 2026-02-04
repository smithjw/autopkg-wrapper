from __future__ import annotations

import logging
import plistlib
import subprocess
from datetime import datetime
from itertools import chain
from pathlib import Path


class Recipe:
    def __init__(self, name: str, post_processors: list = None):
        self.filename = name
        self.error = False
        self.results = {}
        self.updated = False
        self.verified = None
        self.pr_url = None
        self.post_processors = post_processors

        self._keys = None
        self._has_run = False

    @property
    def name(self):
        name = self.filename.split(".")[0]

        return name

    @property
    def identifier(self):
        return self.filename

    def verify_trust_info(self, args):
        verbose_output = ["-vvvv"] if args.debug else []
        prefs_file = (
            ["--prefs", args.autopkg_prefs.as_posix()] if args.autopkg_prefs else []
        )
        autopkg_bin = getattr(args, "autopkg_bin", "/usr/local/bin/autopkg")
        cmd = (
            [autopkg_bin, "verify-trust-info", self.filename]
            + verbose_output
            + prefs_file
        )
        logging.debug(f"cmd: {cmd}")

        if getattr(args, "dry_run", False):
            logging.info("Dry run: would verify trust info for %s", self.identifier)
            return self.verified

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            self.verified = True
        else:
            self.results["message"] = (result.stderr or "").strip()
            self.verified = False
        return self.verified

    def update_trust_info(self, args):
        prefs_file = (
            ["--prefs", args.autopkg_prefs.as_posix()] if args.autopkg_prefs else []
        )
        autopkg_bin = getattr(args, "autopkg_bin", "/usr/local/bin/autopkg")
        cmd = [autopkg_bin, "update-trust-info", self.filename] + prefs_file
        logging.debug(f"cmd: {cmd}")

        if getattr(args, "dry_run", False):
            logging.info("Dry run: would update trust info for %s", self.identifier)
            return

        # Fail loudly if this exits 0
        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError as e:
            logging.error(str(e))
            raise e

    def _parse_report(self, report):
        with open(report, "rb") as f:
            report_data = plistlib.load(f)

        failed_items = report_data.get("failures", [])
        imported_items = []
        if report_data["summary_results"]:
            # This means something happened
            munki_results = report_data["summary_results"].get(
                "munki_importer_summary_result", {}
            )
            imported_items.extend(munki_results.get("data_rows", []))

        return {"imported": imported_items, "failed": failed_items}

    def run(self, args):
        if getattr(args, "dry_run", False):
            autopkg_bin = getattr(args, "autopkg_bin", "/usr/local/bin/autopkg")
            prefs_file = (
                ["--prefs", args.autopkg_prefs.as_posix()] if args.autopkg_prefs else []
            )
            verbose_output = ["-vvvv"] if args.debug else []
            post_processor_cmd = (
                list(
                    chain.from_iterable(
                        [("--post", processor) for processor in self.post_processors]
                    )
                )
                if self.post_processors
                else []
            )
            report_dir = Path("/private/tmp/autopkg")
            report_time = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
            report_name = Path(f"{self.identifier}-{report_time}.plist")
            report = report_dir / report_name
            cmd = (
                [autopkg_bin, "run", self.filename, "--report-plist", report]
                + verbose_output
                + prefs_file
                + post_processor_cmd
            )
            logging.info("Dry run: would run recipe %s", self.identifier)
            logging.debug(f"cmd: {cmd}")
            return self
        if self.verified is False:
            self.error = True
            self.results["failed"] = True
            self.results["imported"] = ""
        else:
            report_dir = Path("/private/tmp/autopkg")
            report_time = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
            report_name = Path(f"{self.identifier}-{report_time}.plist")

            report_dir.mkdir(parents=True, exist_ok=True)
            report = report_dir / report_name
            report.touch(exist_ok=True)

            try:
                prefs_file = (
                    ["--prefs", args.autopkg_prefs.as_posix()]
                    if args.autopkg_prefs
                    else []
                )
                verbose_output = ["-vvvv"] if args.debug else []
                post_processor_cmd = (
                    list(
                        chain.from_iterable(
                            [
                                ("--post", processor)
                                for processor in self.post_processors
                            ]
                        )
                    )
                    if self.post_processors
                    else []
                )
                autopkg_bin = getattr(args, "autopkg_bin", "/usr/local/bin/autopkg")
                cmd = (
                    [autopkg_bin, "run", self.filename, "--report-plist", report]
                    + verbose_output
                    + prefs_file
                    + post_processor_cmd
                )
                logging.debug(f"cmd: {cmd}")

                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    report_info = self._parse_report(report)
                    self.results = report_info
                else:
                    self.error = True
                    self.results["failed"] = True
                    self.results["message"] = (result.stderr or "").strip()
                    self.results["imported"] = ""
            except Exception as e:  # pylint: disable=broad-exception-caught
                logging.error(f"Recipe run failed: {e}")
                self.error = True
                self.results["failed"] = True
                self.results["message"] = (result.stderr or "").strip()
                self.results["imported"] = ""

        return self

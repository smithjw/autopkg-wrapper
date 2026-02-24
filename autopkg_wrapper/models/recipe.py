from __future__ import annotations

import logging
import plistlib
import subprocess
from datetime import datetime
from itertools import chain
from pathlib import Path


class Recipe:
    def __init__(self, name: str, post_processors: list = None):
        """Initialize a Recipe instance.

        Args:
            name: Recipe name without extension (e.g., "Firefox.upload.jamf")
            post_processors: Optional list of AutoPkg post processors
        """
        self.name = name  # Recipe name without extension (e.g., "Firefox.upload.jamf")
        self.filename = (
            None  # Filename with extension (e.g., "Firefox.upload.jamf.recipe.yaml")
        )
        self.error = False
        self.results = {}
        self.updated = False
        self.verified = None
        self.pr_url = None
        self.post_processors = post_processors

        self._keys = None
        self._has_run = False

    @property
    def short_name(self):
        """Get the short name (first part before dot).

        Returns:
            str: Short name (e.g., "Firefox" from "Firefox.upload.jamf")
        """
        return self.name.split(".")[0]

    @property
    def identifier(self):
        """Get the recipe identifier.

        Currently returns the recipe name for backwards compatibility.

        TODO: This should parse and return the actual Identifier field from the
        recipe file (e.g., "com.github.autopkg.download.Firefox") instead of
        just returning the filename-based name.

        Returns:
            str: Recipe identifier (currently same as self.name)
        """
        return self.name

    def verify_trust_info(self, args):
        verbose_output = ["-vvvv"] if args.debug else []
        prefs_file = (
            ["--prefs", args.autopkg_prefs.as_posix()] if args.autopkg_prefs else []
        )
        cmd = (
            [args.autopkg_bin, "verify-trust-info", self.name]
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
        cmd = [args.autopkg_bin, "update-trust-info", self.name] + prefs_file
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

        # Tidy the recipe file if it's a YAML recipe
        self._tidy_recipe_after_trust_update(args)

    def _tidy_recipe_after_trust_update(self, args):
        """Tidy YAML recipe files after trust info update."""
        # Find the recipe file path first
        recipe_path = self._find_recipe_file_path(args)
        if not recipe_path or not recipe_path.exists():
            logging.debug(f"Could not find recipe file to tidy: {self.name}")
            return

        # Check if the actual file is a YAML file
        if not str(recipe_path).endswith(".yaml"):
            logging.debug(
                f"Skipping tidy for non-YAML recipe: {self.name} (file: {recipe_path.name})"
            )
            return

        # Run tidy function
        try:
            from autopkg_wrapper.utils.autopkg_recipe_tidy import tidy_yaml_recipe

            logging.info(f"Tidying recipe file: {recipe_path}")
            success = tidy_yaml_recipe(recipe_path, recipe_path)
            if success:
                logging.debug(f"Successfully tidied recipe: {self.name}")
            else:
                logging.warning(f"Failed to tidy recipe: {self.name}")
        except ImportError as e:
            logging.warning(
                f"Could not import recipe tidy utility (ruamel.yaml may be missing): {e}"
            )
        except Exception as e:
            logging.warning(f"Failed to tidy recipe {self.name}: {e}")

    def _find_recipe_file_path(self, args) -> Path | None:
        """Find the full path to the recipe file."""
        import json

        # Try to get recipe override directory from args or prefs
        recipe_override_dir = None

        if getattr(args, "overrides_repo_path", None):
            recipe_override_dir = Path(args.overrides_repo_path)
            logging.debug(f"Using overrides_repo_path: {recipe_override_dir}")
        elif getattr(args, "autopkg_prefs", None):
            autopkg_prefs_path = Path(args.autopkg_prefs).resolve()
            try:
                if autopkg_prefs_path.suffix == ".json":
                    with open(autopkg_prefs_path) as f:
                        autopkg_prefs = json.load(f)
                elif autopkg_prefs_path.suffix == ".plist":
                    autopkg_prefs = plistlib.loads(autopkg_prefs_path.read_bytes())
                else:
                    return None

                recipe_override_dir = Path(
                    autopkg_prefs.get("RECIPE_OVERRIDE_DIRS", "")
                ).resolve()
                logging.debug(
                    f"Using RECIPE_OVERRIDE_DIRS from prefs: {recipe_override_dir}"
                )
            except Exception as e:
                logging.debug(f"Failed to read autopkg prefs: {e}")
                return None
        else:
            # Try default location
            user_home = Path.home()
            autopkg_prefs_path = (
                user_home / "Library/Preferences/com.github.autopkg.plist"
            )
            if autopkg_prefs_path.is_file():
                try:
                    autopkg_prefs = plistlib.loads(
                        autopkg_prefs_path.resolve().read_bytes()
                    )
                    recipe_override_dir = Path(
                        autopkg_prefs.get("RECIPE_OVERRIDE_DIRS", "")
                    ).resolve()
                    logging.debug(
                        f"Using RECIPE_OVERRIDE_DIRS from default prefs: {recipe_override_dir}"
                    )
                except Exception as e:
                    logging.debug(f"Failed to read default autopkg prefs: {e}")
                    return None

        if not recipe_override_dir or not recipe_override_dir.exists():
            logging.debug(f"Recipe override directory not found: {recipe_override_dir}")
            return None

        # Search for the recipe file with common extensions
        # Recipe files can be: Name.recipe.yaml, Name.recipe, Name.recipe.plist
        possible_extensions = [".recipe.yaml", ".recipe", ".recipe.plist"]

        for ext in possible_extensions:
            recipe_file = recipe_override_dir / f"{self.name}{ext}"
            if recipe_file.exists():
                logging.debug(f"Found recipe file: {recipe_file}")
                return recipe_file

        # Search in subdirectories
        logging.debug(
            f"Searching subdirectories of {recipe_override_dir} for {self.name}"
        )
        for root, _dirs, files in recipe_override_dir.walk():
            for ext in possible_extensions:
                full_name = f"{self.name}{ext}"
                if full_name in files:
                    found_path = root / full_name
                    logging.debug(f"Found recipe file in subdirectory: {found_path}")
                    return found_path

        logging.debug(f"Recipe file not found for {self.name}")
        return None

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
                [args.autopkg_bin, "run", self.name, "--report-plist", report]
                + verbose_output
                + prefs_file
                + post_processor_cmd
            )
            logging.info("Dry run: would run recipe %s", self.identifier)
            logging.debug(f"cmd: {cmd}")
            return self
        if self.verified is False:
            self.error = True
            self.results["failed"] = [
                {"message": self.results.get("message", "Trust verification failed")}
            ]
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
                cmd = (
                    [args.autopkg_bin, "run", self.name, "--report-plist", report]
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
                    error_message = (result.stderr or "").strip()
                    self.results["failed"] = [{"message": error_message}]
                    self.results["imported"] = ""
            except Exception as e:  # pylint: disable=broad-exception-caught
                logging.error(f"Recipe run failed: {e}")
                self.error = True
                error_message = (
                    (result.stderr or "").strip() if "result" in locals() else str(e)
                )
                self.results["failed"] = [{"message": error_message}]
                self.results["imported"] = ""

        return self

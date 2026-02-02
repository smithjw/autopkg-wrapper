#!/usr/bin/env python3
import json
import logging
import plistlib
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from itertools import chain
from pathlib import Path

import autopkg_wrapper.utils.git_functions as git
from autopkg_wrapper.notifier import slack
from autopkg_wrapper.utils.args import setup_args
from autopkg_wrapper.utils.logging import setup_logger
from autopkg_wrapper.utils.recipe_ordering import order_recipe_list
from autopkg_wrapper.utils.report_processor import process_reports


class Recipe(object):
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

    def verify_trust_info(self, args):
        verbose_output = ["-vvvv"] if args.debug else None
        prefs_file = (
            ["--prefs", args.autopkg_prefs.as_posix()] if args.autopkg_prefs else None
        )
        cmd = ["/usr/local/bin/autopkg", "verify-trust-info", self.filename]
        cmd = cmd + verbose_output if verbose_output else cmd
        cmd = cmd + prefs_file if prefs_file else cmd
        cmd = " ".join(cmd)
        logging.debug(f"cmd: {str(cmd)}")

        p = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True
        )
        (output, err) = p.communicate()
        p_status = p.wait()
        if p_status == 0:
            self.verified = True
        else:
            err = err.decode()
            self.results["message"] = err
            self.verified = False
        return self.verified

    def update_trust_info(self, args):
        prefs_file = (
            ["--prefs", args.autopkg_prefs.as_posix()] if args.autopkg_prefs else None
        )
        cmd = ["/usr/local/bin/autopkg", "update-trust-info", self.filename]
        cmd = cmd + prefs_file if prefs_file else cmd
        cmd = " ".join(cmd)
        logging.debug(f"cmd: {str(cmd)}")

        # Fail loudly if this exits 0
        try:
            subprocess.check_call(cmd, shell=True)
        except subprocess.CalledProcessError as e:
            logging.error(e.stderr)
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
        if self.verified is False:
            self.error = True
            self.results["failed"] = True
            self.results["imported"] = ""
        else:
            report_dir = Path("/private/tmp/autopkg")
            report_time = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
            report_name = Path(f"{self.name}-{report_time}.plist")

            report_dir.mkdir(parents=True, exist_ok=True)
            report = report_dir / report_name
            report.touch(exist_ok=True)

            try:
                prefs_file = (
                    ["--prefs", args.autopkg_prefs.as_posix()]
                    if args.autopkg_prefs
                    else None
                )
                verbose_output = ["-vvvv"] if args.debug else None
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
                    else None
                )
                cmd = [
                    "/usr/local/bin/autopkg",
                    "run",
                    self.filename,
                    "--report-plist",
                    str(report),
                ]
                cmd = cmd + post_processor_cmd if post_processor_cmd else cmd
                cmd = cmd + verbose_output if verbose_output else cmd
                cmd = cmd + prefs_file if prefs_file else cmd
                cmd = " ".join(cmd)

                logging.debug(f"cmd: {str(cmd)}")

                subprocess.check_call(cmd, shell=True)

            except subprocess.CalledProcessError:
                self.error = True

            self._has_run = True
            self.results = self._parse_report(report)
            if not self.results["failed"] and not self.error:
                self.updated = True

        return self.results


def get_override_repo_info(args):
    if args.overrides_repo_path:
        recipe_override_dirs = args.overrides_repo_path

    else:
        logging.debug("Trying to determine overrides dir from default paths")

        if args.autopkg_prefs:
            autopkg_prefs_path = Path(args.autopkg_prefs).resolve()

            if autopkg_prefs_path.suffix == ".json":
                with open(autopkg_prefs_path, "r") as f:
                    autopkg_prefs = json.load(f)
            elif autopkg_prefs_path.suffix == ".plist":
                autopkg_prefs = plistlib.loads(autopkg_prefs_path.read_bytes())
        else:
            user_home = Path.home()
            autopkg_prefs_path = (
                user_home / "Library/Preferences/com.github.autopkg.plist"
            )

            if autopkg_prefs_path.is_file():
                autopkg_prefs = plistlib.loads(
                    autopkg_prefs_path.resolve().read_bytes()
                )

        logging.debug(f"autopkg prefs path: {autopkg_prefs_path}")
        logging.debug(f"autopkg prefs: {autopkg_prefs}")
        recipe_override_dirs = Path(autopkg_prefs["RECIPE_OVERRIDE_DIRS"]).resolve()

    if Path(recipe_override_dirs / ".git").is_dir():
        override_repo_path = recipe_override_dirs
    elif Path(recipe_override_dirs.parent / ".git").is_dir():
        override_repo_path = recipe_override_dirs.parent

    logging.debug(f"Override Repo Path: {override_repo_path}")

    override_repo_git_work_tree = f"--work-tree={override_repo_path}"
    override_repo_git_git_dir = f"--git-dir={override_repo_path / '.git'}"
    override_repo_url, override_repo_remote_ref = git.get_repo_info(
        override_repo_git_git_dir
    )

    git_info = {
        "override_repo_path": override_repo_path,
        "override_repo_url": override_repo_url,
        "override_repo_remote_ref": override_repo_remote_ref,
        "__work_tree": override_repo_git_work_tree,
        "__git_dir": override_repo_git_git_dir,
        "override_trust_branch": args.branch_name,
        "github_token": args.github_token,
        "create_pr": args.create_pr,
    }

    logging.debug(git_info)
    return git_info


def update_recipe_repo(recipe, git_info, disable_recipe_trust_check, args):
    logging.debug(f"recipe.verified: {recipe.verified}")
    logging.debug(f"disable_recipe_trust_check: {disable_recipe_trust_check}")

    match recipe.verified:
        case True:
            logging.debug("Not updating repo as recipe has been verified")
            return
        case False | None if disable_recipe_trust_check:
            logging.debug("Not updating repo as recipe verification has been disabled")
            return
        case False:
            logging.debug("Updating repo as recipe verification failed")
            current_branch = git.get_current_branch(git_info)

            if args.disable_git_commands:
                logging.info(
                    "Not runing git commands as --disable-git-commands has been set"
                )
                return

            if current_branch != git_info["override_trust_branch"]:
                logging.debug(
                    f"override_trust_branch: {git_info['override_trust_branch']}"
                )
                git.create_branch(git_info)

            git.stage_recipe(git_info)
            git.commit_recipe(
                git_info, message=f"Updating Trust Info for {recipe.name}"
            )
            git.pull_branch(git_info)
            git.push_branch(git_info)

            return


def parse_recipe_list(recipes, recipe_file, post_processors, args):
    """Parse recipe inputs into a common list of recipe names.

    The arguments assume that `recipes` and `recipe_file` are mutually exclusive.
    If `args.recipe_processing_order` is provided, the list is re-ordered before
    creating `Recipe` objects.
    """
    recipe_list = None

    logging.info(f"Recipes: {recipes}") if recipes else None
    logging.info(f"Recipe List: {recipe_file}") if recipe_file else None

    if recipe_file:
        if recipe_file.suffix == ".json":
            with open(recipe_file, "r") as f:
                recipe_list = json.load(f)
        elif recipe_file.suffix == ".txt":
            with open(recipe_file, "r") as f:
                recipe_list = f.read().splitlines()
    if recipes:
        if isinstance(recipes, list):
            recipe_list = recipes
        elif isinstance(recipes, str):
            if recipes.find(",") != -1:
                # Assuming recipes separated by commas
                recipe_list = [
                    recipe.strip() for recipe in recipes.split(",") if recipe
                ]
            else:
                # Assuming recipes separated by space
                recipe_list = [
                    recipe.strip() for recipe in recipes.split(" ") if recipe
                ]

    if recipe_list is None:
        logging.error(
            """Please provide recipes to run via the following methods:
    --recipes recipe_one.download recipe_two.download
    --recipe-file path/to/recipe_list.json
    Comma separated list in the AUTOPKG_RECIPES env variable"""
        )
        sys.exit(1)

    if args.recipe_processing_order:
        recipe_list = order_recipe_list(
            recipe_list=recipe_list, order=args.recipe_processing_order
        )

    logging.info(f"Processing {len(recipe_list)} recipes.")
    recipe_map = [Recipe(name, post_processors=post_processors) for name in recipe_list]

    return recipe_map


def parse_post_processors(post_processors):
    """Parsing list of post_processors"""
    logging.debug("Parsing post processors")

    post_processors_list = None

    match post_processors:
        case None:
            logging.debug("No post processors defined")
        case []:
            logging.debug("Found an empty list for post processors")
        case list():
            post_processors_list = post_processors
        case str() if post_processors.find(",") != -1:
            post_processors_list = [
                post_processor.strip()
                for post_processor in post_processors.split(",")
                if post_processor.strip()
            ]
        case str():
            post_processors_list = [
                post_processor.strip()
                for post_processor in post_processors.split(" ")
                if post_processor.strip()
            ]

    logging.info(
        f"Post Processors List: {post_processors_list}"
    ) if post_processors_list else None

    return post_processors_list


def process_recipe(recipe, disable_recipe_trust_check, args):
    if disable_recipe_trust_check:
        logging.debug("Setting Recipe verification to None")
        recipe.verified = None
    else:
        logging.debug("Checking Recipe verification")
        recipe.verify_trust_info(args)

    match recipe.verified:
        case False | None if disable_recipe_trust_check:
            logging.debug("Running Recipe without verification")
            recipe.run(args)
        case True:
            logging.debug("Running Recipe after successful verification")
            recipe.run(args)
        case False:
            recipe.update_trust_info(args)

    return recipe


def main():
    args = setup_args()
    setup_logger(args.debug if args.debug else False)
    logging.info("Running autopkg_wrapper")

    override_repo_info = get_override_repo_info(args)

    post_processors_list = parse_post_processors(post_processors=args.post_processors)
    recipe_list = parse_recipe_list(
        recipes=args.recipes,
        recipe_file=args.recipe_file,
        post_processors=post_processors_list,
        args=args,
    )

    failed_recipes = []

    # Run recipes concurrently using a thread pool to parallelize subprocess calls
    max_workers = max(1, int(getattr(args, "concurrency", 1)))
    logging.info(f"Running recipes with concurrency={max_workers}")

    def run_one(r: Recipe):
        logging.info(f"Processing Recipe: {r.name}")
        process_recipe(
            recipe=r,
            disable_recipe_trust_check=args.disable_recipe_trust_check,
            args=args,
        )
        # Git updates and notifications are applied serially after all recipes finish
        return r

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(run_one, r) for r in recipe_list]
        for fut in as_completed(futures):
            r = fut.result()
            if r.error or r.results.get("failed"):
                failed_recipes.append(r)

    # Apply git updates serially to avoid branch/commit conflicts when concurrency > 1
    for r in recipe_list:
        update_recipe_repo(
            git_info=override_repo_info,
            recipe=r,
            disable_recipe_trust_check=args.disable_recipe_trust_check,
            args=args,
        )

    # Send notifications serially to simplify rate limiting and ordering
    if args.slack_token:
        for r in recipe_list:
            slack.send_notification(recipe=r, token=args.slack_token)

    # Optionally open a PR for updated trust information
    if args.create_pr and recipe_list:
        # Choose a representative recipe for the PR title/body
        rep_recipe = next(
            (r for r in recipe_list if r.updated is True or r.verified is False),
            recipe_list[0],
        )
        pr_url = git.create_pull_request(git_info=override_repo_info, recipe=rep_recipe)
        logging.info(f"Created Pull Request for trust info updates: {pr_url}")

    # Create GitHub issue for failed recipes
    if args.create_issues and failed_recipes and args.github_token:
        issue_url = git.create_issue_for_failed_recipes(
            git_info=override_repo_info, failed_recipes=failed_recipes
        )
        logging.info(f"Created GitHub issue for failed recipes: {issue_url}")

    # Optionally process reports after running recipes
    if getattr(args, "process_reports", False):
        rc = process_reports(
            zip_file=getattr(args, "reports_zip", None),
            extract_dir=getattr(
                args, "reports_extract_dir", "autopkg_reports_summary/reports"
            ),
            reports_dir=(getattr(args, "reports_dir", None) or "/private/tmp/autopkg"),
            environment="",
            run_date=getattr(args, "reports_run_date", ""),
            out_dir=getattr(args, "reports_out_dir", "autopkg_reports_summary/summary"),
            debug=bool(getattr(args, "debug", False)),
            strict=bool(getattr(args, "reports_strict", False)),
        )
        if rc:
            sys.exit(rc)

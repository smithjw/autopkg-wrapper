#!/usr/bin/env python3
import json
import logging
import plistlib
import subprocess
import sys
from datetime import datetime
from itertools import chain
from pathlib import Path

import autopkg_wrapper.utils.git_functions as git
from autopkg_wrapper.notifier import slack
from autopkg_wrapper.utils.args import setup_args
from autopkg_wrapper.utils.logging import setup_logger


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

    def verify_trust_info(self, debug):
        verbose_output = ["-vvvv"]
        cmd = ["/usr/local/bin/autopkg", "verify-trust-info", self.filename]
        cmd = cmd + verbose_output if debug else cmd
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

    def update_trust_info(self):
        cmd = ["/usr/local/bin/autopkg", "update-trust-info", self.filename]
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

    def run(self, debug):
        if self.verified is False:
            self.error = True
            self.results["failed"] = True
            self.results["imported"] = ""
        else:
            report_dir = Path("/tmp/autopkg")
            report_time = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
            report_name = Path(f"{self.name}-{report_time}.plist")

            report_dir.mkdir(parents=True, exist_ok=True)
            report = report_dir / report_name
            report.touch(exist_ok=True)

            try:
                post_processor_cmd = list(chain.from_iterable([("--post", processor) for processor in self.post_processors])) if self.post_processors else None
                verbose_output = ["-vvvv"]
                cmd = [
                    "/usr/local/bin/autopkg",
                    "run",
                    self.filename,
                    "--report-plist",
                    str(report),
                ]
                cmd = cmd + post_processor_cmd if post_processor_cmd else cmd
                cmd = cmd + verbose_output if debug else cmd
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
        user_home = Path.home()
        autopkg_prefs_path = user_home / "Library/Preferences/com.github.autopkg.plist"

        if autopkg_prefs_path.is_file():
            autopkg_prefs = plistlib.loads(autopkg_prefs_path.resolve().read_bytes())

        recipe_override_dirs = Path(autopkg_prefs["RECIPE_OVERRIDE_DIRS"]).resolve()

    if Path(recipe_override_dirs / ".git").is_dir():
        override_repo_path = recipe_override_dirs
    elif Path(recipe_override_dirs.parent / ".git").is_dir():
        override_repo_path = recipe_override_dirs.parent

    logging.debug(f"Override Repo Path: {override_repo_path}")

    override_repo_git_work_tree = f"--work-tree={override_repo_path}"
    override_repo_git_git_dir = f"--git-dir={override_repo_path / ".git"}"
    override_repo_url, override_repo_remote_ref = git.get_repo_info(override_repo_git_git_dir)

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
                logging.info("Not runing git commands as --disable-git-commands has been set")
                return

            if current_branch != git_info["override_trust_branch"]:
                logging.debug(f"override_trust_branch: {git_info["override_trust_branch"]}")
                git.create_branch(git_info)

            git.stage_recipe(git_info)
            git.commit_recipe(git_info, message=f"Updating Trust Info for {recipe.name}")
            git.pull_branch(git_info)
            git.push_branch(git_info)

            return


def parse_recipe_list(recipes, recipe_file, post_processors):
    """Parsing list of recipes into a common format"""
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
                recipe_list = [recipe.strip() for recipe in recipes.split(",") if recipe]
            else:
                # Assuming recipes separated by space
                recipe_list = [recipe.strip() for recipe in recipes.split(" ") if recipe]

    if recipe_list is None:
        logging.error(
            """Please provide recipes to run via the following methods:
    --recipes recipe_one.download recipe_two.download
    --recipe-file path/to/recipe_list.json
    Comma separated list in the AUTOPKG_RECIPES env variable"""
        )
        sys.exit(1)

    logging.info(f"Processing the following recipes: {recipe_list}")
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
            post_processors_list = [post_processor.strip() for post_processor in post_processors.split(",") if post_processor.strip()]
        case str():
            post_processors_list = [post_processor.strip() for post_processor in post_processors.split(" ") if post_processor.strip()]

    logging.info(f"Post Processors List: {post_processors_list}") if post_processors_list else None

    return post_processors_list


def process_recipe(recipe, disable_recipe_trust_check, debug):
    if disable_recipe_trust_check:
        logging.debug("Setting Recipe verification to None")
        recipe.verified = None
    else:
        logging.debug("Checking Recipe verification")
        recipe.verify_trust_info(debug)

    match recipe.verified:
        case False | None if disable_recipe_trust_check:
            logging.debug("Running Recipe without verification")
            recipe.run(debug)
        case True:
            logging.debug("Running Recipe after successful verification")
            recipe.run(debug)
        case False:
            recipe.update_trust_info()

    return recipe


def main():
    args = setup_args()
    setup_logger(args.debug if args.debug else False)
    logging.info("Running autopkg_wrapper")

    override_repo_info = get_override_repo_info(args)

    post_processors_list = parse_post_processors(post_processors=args.post_processors)
    recipe_list = parse_recipe_list(recipes=args.recipes, recipe_file=args.recipe_file, post_processors=post_processors_list)

    for recipe in recipe_list:
        logging.info(f"Processing Recipe: {recipe.name}")
        process_recipe(recipe=recipe, disable_recipe_trust_check=args.disable_recipe_trust_check, debug=args.debug)
        update_recipe_repo(git_info=override_repo_info, recipe=recipe, disable_recipe_trust_check=args.disable_recipe_trust_check, args=args)
        slack.send_notification(recipe=recipe, token=args.slack_token) if args.slack_token else None

    recipe.pr_url = git.create_pull_request(git_info=override_repo_info, recipe=recipe) if args.create_pr else None


if __name__ == "__main__":
    main()

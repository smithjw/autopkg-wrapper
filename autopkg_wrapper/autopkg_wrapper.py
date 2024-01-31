#!/usr/bin/env python3
import logging
import plistlib
import subprocess
import sys
from pathlib import Path

import autopkg_wrapper.utils.git_functions as git
from autopkg_wrapper.notifier import slack
from autopkg_wrapper.utils.args import setup_args
from autopkg_wrapper.utils.logging import setup_logger


class Recipe(object):
    def __init__(self, name):
        self.filename = name
        self.error = False
        self.results = {}
        self.updated = False
        self.verified = None
        self.pr_url = None

        self._keys = None
        self._has_run = False

    @property
    def name(self):
        name = self.filename.split(".")[0]

        return name

    def verify_trust_info(self):
        cmd = ["/usr/local/bin/autopkg", "verify-trust-info", self.filename, "-vv"]
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

    def run(self):
        if self.verified is False:
            self.error = True
            self.results["failed"] = True
            self.results["imported"] = ""
        else:
            report = Path("/tmp/autopkg.plist")
            report.touch(exist_ok=True)

            try:
                cmd = [
                    "/usr/local/bin/autopkg",
                    "run",
                    self.filename,
                    "-vv",
                    "--post",
                    "io.github.hjuutilainen.VirusTotalAnalyzer/VirusTotalAnalyzer",
                    "--report-plist",
                    str(report),
                ]
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
    if args.autopkg_overrides_repo_path:
        recipe_override_dirs = args.autopkg_overrides_repo_path

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


def update_recipe_repo(recipe, git_info):
    if recipe.verified:
        return

    current_branch = git.get_current_branch(git_info).stdout.strip()

    if current_branch != git_info["override_trust_branch"]:
        git.create_branch(git_info)

    if recipe.verified is False:
        git.stage_recipe(git_info)
        git.commit_recipe(git_info, message=f"Updating Trust Info for {recipe.name}")
        git.pull_branch(git_info)
        git.push_branch(git_info)


def parse_recipe_list(recipes, recipe_file):
    """Parsing list of recipes into a common format"""
    recipe_list = None

    logging.debug(f"Recipes: {recipes}") if recipes else None
    logging.debug(f"Recipe List: {recipe_file}") if recipe_file else None

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
            """Please provide a recipe to run via the following methods:
    --recipes
    --recipe-list
    Comma separated list in the AUTOPKG_RECIPES env variable"""
        )
        sys.exit(1)

    recipe_map = map(Recipe, recipe_list)

    return recipe_map


def process_recipe(recipe, override_trust):
    if override_trust:
        recipe.verify_trust_info()
        logging.debug(f"Recipe Verification: {recipe.verified}")

    if recipe.verified in (True, None):
        recipe.run()
    elif recipe.verified is False:
        recipe.update_trust_info()

    return recipe


def main():
    args = setup_args()
    setup_logger(args.debug if args.debug else False)
    logging.info("Running autopkg_wrapper")

    override_repo_info = get_override_repo_info(args)

    recipe_list = parse_recipe_list(recipes=args.recipes, recipe_file=args.recipe_file)

    for recipe in recipe_list:
        logging.debug(f"Processing {recipe.name}")
        process_recipe(recipe=recipe, override_trust=args.override_trust)
        update_recipe_repo(git_info=override_repo_info, recipe=recipe)
        slack.send_notification(recipe=recipe, token=args.slack_token) if args.slack_token else None

    recipe.pr_url = git.create_pull_request(git_info=override_repo_info, recipe=recipe) if args.create_pr else None


if __name__ == "__main__":
    main()

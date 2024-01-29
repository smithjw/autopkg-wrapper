#!/usr/bin/env python3
import logging
import os
import plistlib
import subprocess
import sys
from pathlib import Path

import autopkg_wrapper.utils.git_functions as git
from autopkg_wrapper.notifier import slack
from autopkg_wrapper.utils.args import setup_args
from autopkg_wrapper.utils.logging import setup_logger

AUTOPKG_TRUST_BRANCH = os.getenv("AUTOPKG_TRUST_BRANCH", None)


GITHUB_WORKSPACE = Path(os.getenv("GITHUB_WORKSPACE", "."))
AUTOPKG_ACTIONS_REPO = os.getenv("AUTOPKG_ACTIONS_REPO", "recipes")
RECIPE_OVERRIDE_WORK_TREE = GITHUB_WORKSPACE / AUTOPKG_ACTIONS_REPO
RECIPE_OVERRIDE_REPO = GITHUB_WORKSPACE / AUTOPKG_ACTIONS_REPO / ".git"
RECIPE_OVERRIDE_DIRS = GITHUB_WORKSPACE / AUTOPKG_ACTIONS_REPO / "overrides"


class Recipe(object):
    def __init__(self, path):
        self.filename = path
        self.error = False
        self.results = {}
        self.updated = False
        self.verified = None
        self.pr_url = None

        self._keys = None
        self._has_run = False

    @property
    def branch_name(self):
        name = self.name.split(".")[0]
        branch = "{}_{}".format(name.lower(), "verify_trust")

        return branch

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
            report = "/tmp/autopkg.plist"
            if not os.path.isfile(report):
                # Letting autopkg create them has led to errors on github runners
                Path(report).touch()

            try:
                cmd = [
                    "/usr/local/bin/autopkg",
                    "run",
                    self.filename,
                    "-vv",
                    "--post",
                    "io.github.hjuutilainen.VirusTotalAnalyzer/VirusTotalAnalyzer",
                    "--report-plist",
                    report,
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


### Recipe handling
def check_recipe(recipe, verification_disabled):
    if not verification_disabled:
        recipe.verify_trust_info()
        logging.debug(f"Recipe Verification: {recipe.verified}")
    if recipe.verified in (True, None):
        recipe.run()

    return recipe


def parse_recipe(recipe):
    ## Added this section so that we can run individual recipes
    os.path.splitext(recipe)[1]
    # if ext != ".recipe" and ext != ".yaml":
    #     recipe = recipe + ".recipe"

    recipe = recipe

    return Recipe(recipe)


def main():
    args = setup_args()
    setup_logger(args.debug if args.debug else False)

    logging.info("Running main function")
    recipe = args.recipes
    logging.debug("Debug logging enabled")
    if recipe is None:
        logging.error(
            """Please provide a recipe to run via the following methods:
    --recipes
    --recipe-list
    Comma separated list in the AUTOPKG_RECIPES env variable"""
        )
        sys.exit(1)
    recipe = parse_recipe(recipe)

    logging.debug(f"Recipe Name: {recipe.name}")

    # Testing
    check_recipe(recipe, args.disable_verification)
    # recipe.verified = False

    if not args.disable_verification:
        if recipe.verified is False:
            recipe_git_repo = f"--git-dir={RECIPE_OVERRIDE_REPO}"
            recipe_work_tree = f"--work-tree={RECIPE_OVERRIDE_WORK_TREE}"
            current_branch = git.get_branch(recipe_git_repo).stdout.strip()
            repo_url = git.get_repo_info(recipe_git_repo)[0]
            remote_repo_ref = git.get_repo_info(recipe_git_repo)[1]

            branch_name = (
                AUTOPKG_TRUST_BRANCH if AUTOPKG_TRUST_BRANCH else recipe.branch_name
            )

            logging.debug(f"Git Repo URL: {repo_url}")
            logging.debug(f"Git Remote Repo Ref: {remote_repo_ref}")
            logging.debug(f"Recipe Git Repo: {recipe_git_repo}")
            logging.debug(f"Recipe Working Tree: {recipe_work_tree}")
            logging.debug(f"Current Branch: {current_branch}")
            logging.debug(f"Branch Name: {branch_name}")
            logging.debug(f"Recipe Path: {recipe.path}")

            if current_branch != branch_name:
                git.create_branch(branch_name, recipe_git_repo)

            recipe.update_trust_info()
            git.stage_recipe(recipe_git_repo, recipe_work_tree)
            git.commit_recipe(
                f"Updating Trust Info for {recipe.name}",
                recipe_git_repo,
                recipe_work_tree,
            )
            git.pull_branch(branch_name, recipe_git_repo, recipe_work_tree)
            git.push_branch(branch_name, recipe_git_repo, recipe_work_tree)

            if not AUTOPKG_TRUST_BRANCH:
                # If AUTOPKG_TRUST_BRANCH exists, it was passed in from a GitHub Action and PR creation is handled outside this script
                recipe.pr_url = git.create_pull_request(
                    recipe, repo_url, remote_repo_ref, branch_name, args.github_token
                )

    # Send Slack Notification if Slack token is present
    if args.slack_token:
        slack.send_notification(recipe, args.slack_token)


if __name__ == "__main__":
    main()

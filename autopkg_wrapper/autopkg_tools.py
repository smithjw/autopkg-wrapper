#!/usr/local/bin/managed_python3

# BSD-3-Clause
# Copyright (c) Facebook, Inc. and its affiliates.
# Copyright (c) tig <https://6fx.eu/>.
# Copyright (c) Gusto, Inc.
# Copyright (c) James Smith
#
# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import json
import os
import plistlib
import subprocess
import sys
from optparse import OptionParser
from pathlib import Path

import requests
from github import Github

DEBUG = os.getenv("DEBUG", False)
SLACK_WEBHOOK_TOKEN = os.getenv("SLACK_WEBHOOK_TOKEN", None)
AUTOPKG_TRUST_BRANCH = os.getenv("AUTOPKG_TRUST_BRANCH", None)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", None)

AUTOPKG_RECIPES = os.getenv("AUTOPKG_RECIPES", None)
GITHUB_WORKSPACE = Path(os.getenv("GITHUB_WORKSPACE", "."))
AUTOPKG_ACTIONS_REPO = os.getenv("AUTOPKG_ACTIONS_REPO", "recipes")
RECIPE_OVERRIDE_WORK_TREE = GITHUB_WORKSPACE / AUTOPKG_ACTIONS_REPO
RECIPE_OVERRIDE_REPO = GITHUB_WORKSPACE / AUTOPKG_ACTIONS_REPO / ".git"
RECIPE_OVERRIDE_DIRS = GITHUB_WORKSPACE / AUTOPKG_ACTIONS_REPO / "overrides"


class Recipe(object):
    def __init__(self, path):
        self.filename = path
        self.path = os.path.join(RECIPE_OVERRIDE_DIRS, path)
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
        # cmd = ["/usr/local/bin/autopkg", "verify-trust-info", self.path, "-vv"]
        cmd = ["/usr/local/bin/autopkg", "verify-trust-info", self.filename, "-vv"]
        cmd = " ".join(cmd)

        if DEBUG:
            print("Running " + str(cmd))

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

        if DEBUG:
            print("Running " + str(cmd))

        # Fail loudly if this exits 0
        try:
            subprocess.check_call(cmd, shell=True)
        except subprocess.CalledProcessError as e:
            print(e.stderr)
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
                    # self.path,
                    self.filename,
                    "-vv",
                    "--post",
                    "io.github.hjuutilainen.VirusTotalAnalyzer/VirusTotalAnalyzer",
                    "--report-plist",
                    report,
                ]
                cmd = " ".join(cmd)
                if DEBUG:
                    print("Running " + str(cmd))

                subprocess.check_call(cmd, shell=True)

            except subprocess.CalledProcessError:
                self.error = True

            self._has_run = True
            self.results = self._parse_report(report)
            if not self.results["failed"] and not self.error:
                self.updated = True

        return self.results


### GIT FUNCTIONS
def git_run(*args):
    return subprocess.run(["git"] + list(args), text=True, capture_output=True)


def get_branch(repo):
    current_branch = git_run(repo, "rev-parse", "--abbrev-ref", "HEAD")

    return current_branch


def get_repo_info(repo):
    repo_url = (
        git_run(repo, "config", "--get", "remote.origin.url")
        .stdout.strip()
        .split(".git")[0]
    )
    remote_repo_ref = repo_url.split("https://github.com/")[1]

    return repo_url, remote_repo_ref


def create_branch(branch_name, repo):
    new_branch = git_run(repo, "checkout", "-b", branch_name)

    if DEBUG:
        print(f"Git Branch: {new_branch.stdout.strip()}{new_branch.stderr.strip()}")

    return new_branch


def stage_recipe(repo, work_tree):
    add = git_run(repo, work_tree, "add", "-u")

    if DEBUG:
        print(f"Git Add: {add}")

    return add


def commit_recipe(message, repo, work_tree):
    commit = git_run(repo, work_tree, "commit", "-m", message)

    if DEBUG:
        print(f"Git Commit: {commit.stdout}{commit.stderr.strip()}")

    return commit


def pull_branch(branch_name, repo, work_tree):
    pull = git_run(repo, work_tree, "pull", "--rebase", "origin", branch_name)

    if DEBUG:
        print(f"Git Branch: {pull.stdout.strip()}{pull.stderr.strip()}")

    return pull


def push_branch(branch_name, repo, work_tree):
    push = git_run(repo, work_tree, "push", "-u", "origin", branch_name)

    if DEBUG:
        print(f"Git Push: {push.stdout.strip()}{push.stderr.strip()}")

    return push


def create_pull_request(recipe, repo_url, remote_repo_ref, branch):
    title = f"Update Trust Information: {recipe.name}"
    body = f"""
Recipe Verification information is out-of-date for {recipe.name}.
Please review and merge the updated trust information for this override.
    """

    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(remote_repo_ref)
    pr = repo.create_pull(title=title, body=body, head=branch, base="main")
    pr_url = f"{repo_url}/pull/{pr.number}"

    if DEBUG:
        print(pr_url)

    return pr_url


### Recipe handling
def check_recipe(recipe, opts):
    if not opts.disable_verification:
        recipe.verify_trust_info()
        if DEBUG:
            print(f"Recipe Verification: {recipe.verified}")
    if recipe.verified in (True, None):
        recipe.run()

    return recipe


def parse_recipe(recipe):
    ## Added this section so that we can run individual recipes
    if AUTOPKG_RECIPES:
        ext = os.path.splitext(recipe)[1]
        if ext != ".recipe" and ext != ".yaml":
            recipe = recipe + ".recipe"

    return Recipe(recipe)


def slack_alert(recipe, opts):
    if DEBUG:
        print("Skippingk Slack notification as DEBUG is enabled!")
        return

    if SLACK_WEBHOOK_TOKEN is None:
        print("Skipping Slack Notification as no SLACK_WEBHOOK_TOKEN defined!")
        return

    if recipe.verified is False:
        task_title = f"{recipe.name} failed trust verification"
        task_description = recipe.results["message"]
    elif recipe.error:
        task_title = f"Failed to import {recipe.name}"
        if not recipe.results["failed"]:
            task_description = "Unknown error"
        else:
            task_description = ("Error: {} \n" "Traceback: {} \n").format(
                recipe.results["failed"][0]["message"],
                recipe.results["failed"][0]["traceback"],
            )

            if "No releases found for repo" in task_description:
                # Just no updates
                return
    elif recipe.updated:
        task_title = f"{recipe.name} has been uploaded to Jamf"
        task_description = f"It's time to test {recipe.name}!"
    else:
        # Also no updates
        return

    response = requests.post(
        SLACK_WEBHOOK_TOKEN,
        data=json.dumps(
            {
                "attachments": [
                    {
                        "username": "Autopkg",
                        "as_user": True,
                        "title": task_title,
                        "color": "warning"
                        if not recipe.verified
                        else "good"
                        if not recipe.error
                        else "danger",
                        "text": task_description,
                        "mrkdwn_in": ["text"],
                    }
                ]
            }
        ),
        headers={"Content-Type": "application/json"},
    )
    if response.status_code != 200:
        raise ValueError(
            "Request to slack returned an error %s, the response is:\n%s"
            % (response.status_code, response.text)
        )


def main():
    parser = OptionParser(description="Wrap AutoPkg with git support.")
    parser.add_option(
        "-l", "--list", help="Path to a plist or JSON list of recipe names."
    )
    parser.add_option(
        "-d",
        "--debug",
        action="store_true",
        help="Disables sending Slack alerts and adds more verbosity to output.",
    )
    parser.add_option(
        "-v",
        "--disable_verification",
        action="store_true",
        help="Disables recipe verification.",
    )

    (opts, _) = parser.parse_args()

    global DEBUG
    DEBUG = bool(DEBUG or opts.debug)

    # if DEBUG:
    #     VERBOSITY = "-vvv"
    # else:
    #     VERBOSITY = "-v"

    recipe = AUTOPKG_RECIPES
    if DEBUG:
        print("")
    if recipe is None:
        print("Recipe --list or RECIPE_TO_RUN not provided!")
        sys.exit(1)
    recipe = parse_recipe(recipe)

    if DEBUG:
        print(f"Recipe Name: {recipe.name}")

    # Testing
    check_recipe(recipe, opts)
    # recipe.verified = False

    if not opts.disable_verification:
        if recipe.verified is False:
            recipe_git_repo = f"--git-dir={RECIPE_OVERRIDE_REPO}"
            recipe_work_tree = f"--work-tree={RECIPE_OVERRIDE_WORK_TREE}"
            current_branch = get_branch(recipe_git_repo).stdout.strip()
            repo_url = get_repo_info(recipe_git_repo)[0]
            remote_repo_ref = get_repo_info(recipe_git_repo)[1]

            if AUTOPKG_TRUST_BRANCH:
                branch_name = AUTOPKG_TRUST_BRANCH
            else:
                branch_name = recipe.branch_name

            if DEBUG:
                print(f"Git Repo URL: {repo_url}")
                print(f"Git Remote Repo Ref: {remote_repo_ref}")
                print(f"Recipe Git Repo: {recipe_git_repo}")
                print(f"Recipe Working Tree: {recipe_work_tree}")
                print(f"Current Branch: {current_branch}")
                print(f"Branch Name: {branch_name}")
                print(f"Recipe Path: {recipe.path}")

            if current_branch != branch_name:
                create_branch(branch_name, recipe_git_repo)

            recipe.update_trust_info()
            stage_recipe(recipe_git_repo, recipe_work_tree)
            commit_recipe(
                f"Updating Trust Info for {AUTOPKG_RECIPES}",
                recipe_git_repo,
                recipe_work_tree,
            )
            pull_branch(branch_name, recipe_git_repo, recipe_work_tree)
            push_branch(branch_name, recipe_git_repo, recipe_work_tree)

            if not AUTOPKG_TRUST_BRANCH:
                # If BRANCH_NAME exists, it was passed in from a GitHub Action and PR creation is handled outside this script
                recipe.pr_url = create_pull_request(
                    recipe, repo_url, remote_repo_ref, branch_name
                )

    # Send Slack Notification stating success of run or link to Pull Request
    # slack_alert(recipe, opts)


if __name__ == "__main__":
    main()

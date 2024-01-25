import os
import plistlib
import subprocess
import sys
from pathlib import Path

from github import Github
from notifier import slack
from utils.args import setup_args
from utils.logging import setup_logger

# DEBUG = os.getenv("DEBUG", False)
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
def check_recipe(recipe):
    if not args.disable_verification:
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


def main():
    recipe = AUTOPKG_RECIPES
    if DEBUG:
        print("Debug logging enabled")
    if recipe is None:
        print("Recipe --list or RECIPE_TO_RUN not provided!")
        sys.exit(1)
    recipe = parse_recipe(recipe)

    if DEBUG:
        print(f"Recipe Name: {recipe.name}")

    # Testing
    check_recipe(recipe)
    # recipe.verified = False

    if not args.disable_verification:
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

    # Send Slack Notification if Slack token is present
    if args.slack_token:
        slack.send_notification(recipe, args.slack_token)


if __name__ == "__main__":
    args = setup_args()
    DEBUG = args.debug if args.debug else False
    setup_logger(DEBUG)

    main()

import logging
import subprocess

from github import Github


def git_run(*args):
    return subprocess.run(["git"] + list(args), text=True, capture_output=True)


def git_get_branch(repo):
    current_branch = git_run(repo, "rev-parse", "--abbrev-ref", "HEAD")

    return current_branch


def git_get_repo_info(repo):
    repo_url = (
        git_run(repo, "config", "--get", "remote.origin.url")
        .stdout.strip()
        .split(".git")[0]
    )
    remote_repo_ref = repo_url.split("https://github.com/")[1]

    return repo_url, remote_repo_ref


def git_create_branch(branch_name, repo):
    new_branch = git_run(repo, "checkout", "-b", branch_name)

    logging.debug(f"Git Branch: {new_branch.stdout.strip()}{new_branch.stderr.strip()}")

    return new_branch


def git_stage_recipe(repo, work_tree):
    add = git_run(repo, work_tree, "add", "-u")

    logging.debug(f"Git Add: {add}")

    return add


def git_commit_recipe(message, repo, work_tree):
    commit = git_run(repo, work_tree, "commit", "-m", message)

    logging.debug(f"Git Commit: {commit.stdout}{commit.stderr.strip()}")

    return commit


def git_pull_branch(branch_name, repo, work_tree):
    pull = git_run(repo, work_tree, "pull", "--rebase", "origin", branch_name)

    logging.debug(f"Git Branch: {pull.stdout.strip()}{pull.stderr.strip()}")

    return pull


def git_push_branch(branch_name, repo, work_tree):
    push = git_run(repo, work_tree, "push", "-u", "origin", branch_name)

    logging.debug(f"Git Push: {push.stdout.strip()}{push.stderr.strip()}")

    return push


def git_create_pr(recipe, repo_url, remote_repo_ref, branch, github_token):
    title = f"Update Trust Information: {recipe.name}"
    body = f"""
Recipe Verification information is out-of-date for {recipe.name}.
Please review and merge the updated trust information for this override.
    """

    g = Github(github_token)
    repo = g.get_repo(remote_repo_ref)
    pr = repo.create_pull(title=title, body=body, head=branch, base="main")
    pr_url = f"{repo_url}/pull/{pr.number}"

    logging.debug(f"PR URL: {pr_url}")

    return pr_url

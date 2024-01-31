import logging
import subprocess

from github import Github

# git_info = {
#         "override_repo_path": override_repo_path,
#         "override_repo_url": override_repo_url,
#         "override_repo_remote_ref": override_repo_remote_ref,
#         "__work_tree": override_repo_git_work_tree,
#         "__git_dir": override_repo_git_git_dir,
#         "override_trust_branch": args.branch_name,
#         "github_token": args.github_token,
#         "create_pr": args.create_pr,
#     }


def git_run(*args):
    return subprocess.run(["git"] + list(args), text=True, capture_output=True)


def get_repo_info(override_repo_git_git_dir):
    repo_url = (
        git_run(override_repo_git_git_dir, "config", "--get", "remote.origin.url")
        .stdout.strip()
        .split(".git")[0]
    )
    remote_repo_ref = repo_url.split("https://github.com/")[1]

    logging.debug(f"Repo URL: {repo_url}")
    logging.debug(f"Remote Repo Ref: {remote_repo_ref}")
    return repo_url, remote_repo_ref


def get_current_branch(git_info):
    current_branch = git_run(git_info["__git_dir"], "rev-parse", "--abbrev-ref", "HEAD")
    current_branch = current_branch.stdout.strip()

    logging.debug(f"Current Branch: {current_branch}")
    return current_branch


def create_branch(git_info):
    new_branch = git_run(
        git_info["__git_dir"], "checkout", "-b", git_info["override_trust_branch"]
    )

    logging.debug(f"Git Branch: {new_branch}")
    return new_branch


def stage_recipe(git_info):
    add = git_run(git_info["__git_dir"], git_info["__work_tree"], "add", "-u")

    logging.debug(f"Git Add: {add}")
    return add


def commit_recipe(git_info, message):
    commit = git_run(
        git_info["__git_dir"], git_info["__work_tree"], "commit", "-m", message
    )

    logging.debug(f"Git Commit: {commit}")
    return commit


def pull_branch(git_info):
    pull = git_run(
        git_info["__git_dir"],
        git_info["__work_tree"],
        "pull",
        "--rebase",
        "origin",
        git_info["override_trust_branch"],
    )

    logging.debug(f"Git Branch: {pull}")
    return pull


def push_branch(git_info):
    push = git_run(
        git_info["__git_dir"],
        git_info["__work_tree"],
        "push",
        "-u",
        "origin",
        git_info["override_trust_branch"],
    )

    logging.debug(f"Git Push: {push}")
    return push


def create_pull_request(git_info, recipe):
    title = f"Update Trust Information: {recipe.name}"
    body = f"""
Recipe Verification information is out-of-date for {recipe.name}.
Please review and merge the updated trust information for this override.
    """

    g = Github(git_info["github_token"])
    repo = g.get_repo(git_info["override_repo_remote_ref"])
    pr = repo.create_pull(title=title, body=body, head=git_info["override_trust_branch"], base="main")
    pr_url = f"{git_info["override_repo_url"]}/pull/{pr.number}"

    logging.debug(f"PR URL: {pr_url}")
    return pr_url

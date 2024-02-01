import argparse
import os
from datetime import datetime
from pathlib import Path


def validate_file(arg):
    file_path = Path(arg).resolve()
    file_exists = file_path.exists()

    if file_exists:
        return file_path
    else:
        message = f"Error! This is not valid file: {arg}"
        raise argparse.ArgumentTypeError(message)

def validate_directory(arg):
    dir_path = Path(arg).resolve()
    dir_exists = dir_path.is_dir()

    if dir_exists:
        return dir_path
    else:
        message = f"Error! This is not valid directory: {arg}"
        raise argparse.ArgumentTypeError(message)


def setup_args():
    parser = argparse.ArgumentParser(description="Run autopkg recipes")
    recipe_arguments = parser.add_mutually_exclusive_group()
    recipe_arguments.add_argument(
        "--recipe-file",
        type=validate_file,
        default=None,
        help="Path to a list of recipes to run",
    )
    recipe_arguments.add_argument(
        "--recipes",
        "--recipe",
        nargs="*",
        default=os.getenv("AUTOPKG_RECIPES", None),
        help="Recipes to run with autopkg",
    )
    parser.add_argument(
        "--debug",
        default=os.getenv("DEBUG", False),
        action="store_true",
        help="Enable debug logging when running script",
    )
    parser.add_argument(
        "--override-trust",
        action="store_false",
        help="If set recipe override trust verification will be disabled. (Default: True)",
    )
    parser.add_argument("--slack-token", default=os.getenv("SLACK_WEBHOOK_TOKEN", None), help=argparse.SUPPRESS)
    parser.add_argument("--github-token", default=os.getenv("GITHUB_TOKEN", None))
    parser.add_argument(
        "--branch-name",
        default=os.getenv("AUTOPKG_TRUST_BRANCH", f"fix/update_trust_information/{datetime.now().strftime("%Y-%m-%dT%H-%M-%S")}"),
        help="""
            Branch name to be used recipe overrides have failed their trust verification and need to be updated.
            By default, this will be in the format of \"fix/update_trust_information/YYYY-MM-DDTHH-MM-SS\"
            """,
    )
    parser.add_argument(
        "--create-pr",
        default=os.getenv("CREATE_PR", False),
        action="store_true",
        help="If enabled, autopkg_wrapper will open a PR for updated trust information",
    )
    parser.add_argument(
        "--autopkg-overrides-repo-path",
        default=os.getenv("AUTOPKG_OVERRIDES_REPO_PATH", None),
        type=validate_directory,
        help="""
        The path on disk to the git repository containing the autopkg overrides directory.
        If none is provided, we will try to determine it for you.
        """,
    )

    return parser.parse_args()

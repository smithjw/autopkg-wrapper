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

def validate_bool(arg):
    if isinstance(arg, bool):
        return arg
    elif isinstance(arg, str) and arg.lower() in ['0','false','no', 'f']:
        return False
    elif isinstance(arg, str) and arg.lower() in ['1','true','yes', 't']:
        return True

def setup_args():
    parser = argparse.ArgumentParser(description="Run autopkg recipes")
    recipe_arguments = parser.add_mutually_exclusive_group()
    recipe_arguments.add_argument(
        "--recipe-file",
        type=validate_file,
        default=os.getenv("AW_RECIPE_FILE", None),
        help="Provide the list of recipes to run via a JSON file for easier management.",
    )
    recipe_arguments.add_argument(
        "--recipes",
        nargs="*",
        default=os.getenv("AW_RECIPES", None),
        help="""
            Recipes to run via CLI flag or environment variable. If the '--recipes' flag is used, simply
            provide a space-separated list on the command line:
                `autopkg-wrapper --recipes recipe_one.download recipe_two.download`
            Alternatively, you can provide a space/comma-separated list in the 'AW_RECIPES' environment
            variable:
                `export AW_RECIPES="recipe_one.download recipe_two.download"`
                `export AW_RECIPES="recipe_one.pkg,recipe_two.pkg"`
                `autopkg-wrapper`
            """,
    )
    parser.add_argument(
        "--debug",
        default=validate_bool(os.getenv("AW_DEBUG", False)),
        action="store_true",
        help="Enable debug logging when running script",
    )
    parser.add_argument(
        "--disable-recipe-trust-check",
        action="store_true",
        help="""
            If this option is used, recipe trust verification will not be run prior to a recipe run.
            This does not set FAIL_RECIPES_WITHOUT_TRUST_INFO to No. You will need to set that outside
            of this application.
            """,
    )
    parser.add_argument(
        "--disable-git-commands",
        action="store_true",
        help="""
            If this option is used, git commands won't be run
            """,
    )
    parser.add_argument("--slack-token", default=os.getenv("SLACK_WEBHOOK_TOKEN", None), help=argparse.SUPPRESS)
    parser.add_argument("--github-token", default=os.getenv("GITHUB_TOKEN", None))
    parser.add_argument(
        "--branch-name",
        default=os.getenv("AW_TRUST_BRANCH", f"fix/update_trust_information/{datetime.now().strftime("%Y-%m-%dT%H-%M-%S")}"),
        help="""
            Branch name to be used recipe overrides have failed their trust verification and need to be updated.
            By default, this will be in the format of \"fix/update_trust_information/YYYY-MM-DDTHH-MM-SS\"
            """,
    )
    parser.add_argument(
        "--create-pr",
        default=os.getenv("AW_CREATE_PR", False),
        action="store_true",
        help="If enabled, autopkg_wrapper will open a PR for updated trust information",
    )
    parser.add_argument(
        "--overrides-repo-path",
        default=os.getenv("AW_OVERRIDES_REPO_PATH", None),
        type=validate_directory,
        help="""
        The path on disk to the git repository containing the autopkg overrides directory.
        If none is provided, we will try to determine it for you.
        """,
    )
    parser.add_argument(
        "--post-processors",
        default=os.getenv("AW_POST_PROCESSORS", None),
        nargs="*",
        help="""
        One or more autopkg post processors to run after each recipe execution
        """,
    )

    return parser.parse_args()

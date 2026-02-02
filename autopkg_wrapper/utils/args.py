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
    elif isinstance(arg, str) and arg.lower() in ["0", "false", "no", "f"]:
        return False
    elif isinstance(arg, str) and arg.lower() in ["1", "true", "yes", "t"]:
        return True


def find_github_token():
    if os.getenv("GITHUB_TOKEN", None):
        return os.getenv("GITHUB_TOKEN")
    elif os.getenv("GH_TOKEN", None):
        return os.getenv("GH_TOKEN")
    else:
        return None


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
        "--recipe-processing-order",
        nargs="*",
        default=os.getenv("AW_RECIPE_PROCESSING_ORDER", None),
        help="""
            This option comes in handy if you include additional recipe type names in your overrides and wish them to be processed in a specific order.
            We'll specifically look for these recipe types after the first period (.) in the recipe name.
            Order items can be either a full type suffix (e.g. "upload.jamf") or a partial token (e.g. "upload", "auto_update").
            Partial tokens are matched against the dot-separated segments after the first '.' so recipes like "Foo.epz.auto_update.jamf" will match "auto_update".
            This can also be provided via the 'AW_RECIPE_PROCESSING_ORDER' environment variable as a comma-separated list (e.g. "upload,self_service,auto_update").
            For example, if you have the following recipes to be processed:
                ExampleApp.auto_install.jamf
                ExampleApp.upload.jamf
                ExampleApp.self_service.jamf
            And you want to ensure that the .upload recipes are always processed first, followed by .auto_install, and finally .self_service, you would provide the following processing order:
                `--recipe-processing-order upload.jamf auto_install.jamf self_service.jamf`
            This would ensure that all .upload recipes are processed before any other recipe types.
            Within each recipe type, the recipes will be ordered alphabetically.
            We assume that no extensions are provided (but will strip them if needed - extensions that are stripped include .recipe or .recipe.yaml).
            """,
    )
    parser.add_argument(
        "--autopkg-bin",
        default=os.getenv("AW_AUTOPKG_BIN", "/usr/local/bin/autopkg"),
        help="Path to the autopkg binary (default: /usr/local/bin/autopkg). Can also be set via AW_AUTOPKG_BIN.",
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
    parser.add_argument(
        "--concurrency",
        type=int,
        default=int(os.getenv("AW_CONCURRENCY", "1")),
        help="Number of recipes to run in parallel (default: 1)",
    )
    parser.add_argument(
        "--slack-token",
        default=os.getenv("SLACK_WEBHOOK_TOKEN", None),
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--github-token", default=find_github_token())
    parser.add_argument(
        "--branch-name",
        default=os.getenv(
            "AW_TRUST_BRANCH",
            f"fix/update_trust_information/{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}",
        ),
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
        "--create-issues",
        action="store_true",
        help="Create a GitHub issue for recipes that fail during processing",
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
    parser.add_argument(
        "--autopkg-prefs",
        default=os.getenv("AW_AUTOPKG_PREFS_FILE", None),
        type=validate_file,
        help="""
        Path to the autopkg preferences you'd like to use
        """,
    )

    # Report processing options
    parser.add_argument(
        "--process-reports",
        action="store_true",
        help="Process autopkg report directories or zip and emit markdown summaries",
    )
    parser.add_argument(
        "--reports-zip",
        default=os.getenv("AW_REPORTS_ZIP", None),
        help="Path to an autopkg_report-*.zip to extract and process",
    )
    parser.add_argument(
        "--reports-extract-dir",
        default=os.getenv("AW_REPORTS_EXTRACT_DIR", "autopkg_reports_summary/reports"),
        help="Directory to extract the zip into (default: autopkg_reports_summary/reports)",
    )
    parser.add_argument(
        "--reports-dir",
        default=os.getenv("AW_REPORTS_DIR", None),
        help="Directory of reports to process (if no zip provided)",
    )
    parser.add_argument(
        "--reports-out-dir",
        default=os.getenv("AW_REPORTS_OUT_DIR", "autopkg_reports_summary/summary"),
        help="Directory to write markdown outputs (default: autopkg_reports_summary/summary)",
    )
    parser.add_argument(
        "--reports-run-date",
        default=os.getenv("AW_REPORTS_RUN_DATE", ""),
        help="Run date string to include in the summary",
    )
    parser.add_argument(
        "--reports-strict",
        action="store_true",
        help="Exit non-zero if any errors are detected in processed reports",
    )

    return parser.parse_args()

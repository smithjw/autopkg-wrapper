import argparse
import os
from pathlib import Path


def setup_args():
    parser = argparse.ArgumentParser(description="Run autopkg recipes")
    parser.add_argument(
        "--debug",
        default=os.getenv("DEBUG", False),
        action="store_true",
        help="Enable debug logging when running script",
    )
    parser.add_argument(
        "--recipe-list",
        "-l",
        help="Path to a plist or JSON list of recipe names.",
    )
    parser.add_argument(
        "--recipes",
        "-r",
        nargs="*",
        default=os.getenv("AUTOPKG_RECIPES", None),
        help="Recipes to run with autopkg",
    )
    parser.add_argument(
        "--disable-verification",
        "-v",
        default=False,
        action="store_true",
        help="Disables recipe verification.",
    )
    parser.add_argument(
        "--slack-token", "-s", default=os.getenv("SLACK_WEBHOOK_TOKEN", None)
    )
    parser.add_argument("--github-token", "-g", default=os.getenv("GITHUB_TOKEN", None))
    parser.add_argument(
        "--branch",
        "-b",
        default=os.getenv("AUTOPKG_TRUST_BRANCH", None),
        help="Branch name to be used when updating trust information for autopkg recipe overrides",
    )
    parser.add_argument(
        "--working-directory", "-d", default=Path(os.getenv("GITHUB_WORKSPACE", "."))
    )
    parser.add_argument(
        "--autopkg-overrides-repo",
        "-o",
        default=os.getenv("AUTOPKG_OVERRIDES_REPO", "autopkg-overrides"),
        help="This should be the name of the folder/repo containing the autopkg override directory.",
    )

    return parser.parse_args()

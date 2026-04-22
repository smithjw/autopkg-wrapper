#!/usr/bin/env python3
import glob as glob_module
import json
import logging
import plistlib
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import autopkg_wrapper.utils.git_functions as git
from autopkg_wrapper.models.recipe import Recipe
from autopkg_wrapper.notifier import slack
from autopkg_wrapper.utils.args import setup_args
from autopkg_wrapper.utils.logging import setup_logger
from autopkg_wrapper.utils.recipe_batching import (
    build_recipe_batches,
    describe_recipe_batches,
)
from autopkg_wrapper.utils.recipe_ordering import order_recipe_list
from autopkg_wrapper.utils.report_processor import process_reports


def normalize_recipe_identifier(recipe_input: str) -> str:
    """Normalize a recipe input to just the identifier.

    Handles both recipe identifiers and file paths, stripping path components
    and recipe file extensions.

    Args:
        recipe_input: Recipe identifier or file path

    Returns:
        Normalized recipe identifier (e.g., "Firefox.upload.jamf")

    Examples:
        >>> normalize_recipe_identifier("Firefox.upload.jamf")
        "Firefox.upload.jamf"
        >>> normalize_recipe_identifier("overrides/Firefox/Firefox.upload.jamf.recipe.yaml")
        "Firefox.upload.jamf"
        >>> normalize_recipe_identifier("/path/to/Chrome.download.recipe")
        "Chrome.download"
    """
    # Get just the filename if it's a path
    file_name = Path(recipe_input).name

    # Strip common recipe extensions
    for ext in [".recipe.yaml", ".recipe.plist", ".recipe"]:
        if file_name.endswith(ext):
            return file_name[: -len(ext)]

    # If no extension matched, return the filename as-is
    # (assumes it's already a recipe identifier)
    return file_name


def has_glob_pattern(text: str) -> bool:
    """Check if a string contains glob pattern characters.

    Args:
        text: String to check for glob patterns

    Returns:
        True if the string contains glob pattern characters (*, ?, [, ], **)
    """
    glob_chars = ["*", "?", "[", "]"]
    return any(char in text for char in glob_chars)


def discover_recipes_from_glob(
    pattern: str, base_path: Path | None = None
) -> list[str]:
    """Discover recipe files using glob patterns and extract their identifiers.

    Args:
        pattern: Glob pattern to match recipe files (e.g., "overrides/**/*.recipe.yaml")
        base_path: Base directory to resolve relative patterns (defaults to cwd)

    Returns:
        List of recipe identifiers (e.g., ["Firefox.upload.jamf", "Chrome.download"])
    """
    if base_path:
        pattern = str(Path(base_path) / pattern)

    # Use glob to find matching files
    matched_files = glob_module.glob(pattern, recursive=True)

    if not matched_files:
        logging.warning(f"No recipe files found matching pattern: {pattern}")
        return []

    recipe_identifiers = []
    for file_path in matched_files:
        file_name = Path(file_path).name

        # Strip common recipe extensions to get the identifier
        for ext in [".recipe.yaml", ".recipe.plist", ".recipe"]:
            if file_name.endswith(ext):
                identifier = file_name[: -len(ext)]
                recipe_identifiers.append(identifier)
                break

    logging.info(
        f"Discovered {len(recipe_identifiers)} recipes from pattern: {pattern}"
    )
    logging.debug(f"Recipe identifiers: {recipe_identifiers}")

    return recipe_identifiers


def get_override_repo_info(args):
    if args.overrides_repo_path:
        recipe_override_dirs = args.overrides_repo_path

    else:
        logging.debug("Trying to determine overrides dir from default paths")

        if args.autopkg_prefs:
            autopkg_prefs_path = Path(args.autopkg_prefs).resolve()

            if autopkg_prefs_path.suffix == ".json":
                with open(autopkg_prefs_path) as f:
                    autopkg_prefs = json.load(f)
            elif autopkg_prefs_path.suffix == ".plist":
                autopkg_prefs = plistlib.loads(autopkg_prefs_path.read_bytes())
        else:
            user_home = Path.home()
            autopkg_prefs_path = (
                user_home / "Library/Preferences/com.github.autopkg.plist"
            )

            if autopkg_prefs_path.is_file():
                autopkg_prefs = plistlib.loads(
                    autopkg_prefs_path.resolve().read_bytes()
                )

        logging.debug(f"autopkg prefs path: {autopkg_prefs_path}")
        logging.debug(f"autopkg prefs: {autopkg_prefs}")
        recipe_override_dirs = Path(autopkg_prefs["RECIPE_OVERRIDE_DIRS"]).resolve()

    if Path(recipe_override_dirs / ".git").is_dir():
        override_repo_path = recipe_override_dirs
    elif Path(recipe_override_dirs.parent / ".git").is_dir():
        override_repo_path = recipe_override_dirs.parent

    logging.debug(f"Override Repo Path: {override_repo_path}")

    override_repo_git_work_tree = f"--work-tree={override_repo_path}"
    override_repo_git_git_dir = f"--git-dir={override_repo_path / '.git'}"
    override_repo_url, override_repo_remote_ref = git.get_repo_info(
        override_repo_git_git_dir
    )

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


def update_recipe_repo(recipe, git_info, disable_recipe_trust_check, args):
    if getattr(args, "dry_run", False):
        logging.info(
            "Dry run: would update trust info in override repo for %s",
            recipe.identifier,
        )
        return
    logging.debug(f"recipe.verified: {recipe.verified}")
    logging.debug(f"disable_recipe_trust_check: {disable_recipe_trust_check}")

    match recipe.verified:
        case True:
            logging.debug("Not updating repo as recipe has been verified")
            return
        case False | None if disable_recipe_trust_check:
            logging.debug("Not updating repo as recipe verification has been disabled")
            return
        case False:
            logging.debug("Updating repo as recipe verification failed")
            current_branch = git.get_current_branch(git_info)

            if args.disable_git_commands:
                logging.info(
                    "Not runing git commands as --disable-git-commands has been set"
                )
                return

            if current_branch != git_info["override_trust_branch"]:
                logging.debug(
                    f"override_trust_branch: {git_info['override_trust_branch']}"
                )
                git.create_branch(git_info)

            git.stage_recipe(git_info)
            git.commit_recipe(
                git_info, message=f"Updating Trust Info for {recipe.identifier}"
            )
            git.pull_branch(git_info)
            git.push_branch(git_info)

            return


def parse_recipe_list(recipes, recipe_file, post_processors, args):
    """Parse recipe inputs into a common list of recipe names.

    The arguments assume that `recipes` and `recipe_file` are mutually exclusive.
    If `args.recipe_processing_order` is provided, the list is re-ordered before
    creating `Recipe` objects.
    Supports glob patterns in the recipes argument (e.g., "overrides/**/*.recipe.yaml").
    """
    recipe_list = None

    logging.debug(f"Recipes: {recipes}") if recipes else None
    logging.debug(f"Recipe List: {recipe_file}") if recipe_file else None

    if recipe_file:
        if recipe_file.suffix == ".json":
            with open(recipe_file) as f:
                recipe_list = json.load(f)
        elif recipe_file.suffix in {".yaml", ".yml"}:
            from ruamel.yaml import YAML

            yaml = YAML(typ="safe")
            with open(recipe_file, encoding="utf-8") as f:
                recipe_list = yaml.load(f)
        elif recipe_file.suffix == ".txt":
            with open(recipe_file) as f:
                recipe_list = f.read().splitlines()
    if recipes:
        if isinstance(recipes, list):
            # Check if any item in the list is a glob pattern
            glob_recipes = []
            non_glob_recipes = []

            for recipe in recipes:
                if has_glob_pattern(recipe):
                    # Discover recipes using glob pattern
                    discovered = discover_recipes_from_glob(recipe)
                    glob_recipes.extend(discovered)
                else:
                    non_glob_recipes.append(recipe)

            # Combine non-glob and glob-discovered recipes
            recipe_list = non_glob_recipes + glob_recipes

        elif isinstance(recipes, str):
            # Check if the string contains glob patterns
            if has_glob_pattern(recipes):
                # Single glob pattern string
                recipe_list = discover_recipes_from_glob(recipes)
            elif recipes.find(",") != -1:
                # Assuming recipes separated by commas
                recipe_list = [
                    recipe.strip() for recipe in recipes.split(",") if recipe
                ]
            else:
                # Assuming recipes separated by space
                recipe_list = [
                    recipe.strip() for recipe in recipes.split(" ") if recipe
                ]

    if recipe_list is None:
        logging.error(
            """Please provide recipes to run via the following methods:
    --recipes recipe_one.download recipe_two.download
    --recipes "overrides/**/*.recipe.yaml"
    --recipe-file path/to/recipe_list.json
    Comma separated list in the AW_RECIPES env variable"""
        )
        sys.exit(1)

    if args.recipe_processing_order:
        recipe_list = order_recipe_list(
            recipe_list=recipe_list, order=args.recipe_processing_order
        )

    # Normalize all recipe identifiers (strip paths and extensions)
    recipe_list = [normalize_recipe_identifier(name) for name in recipe_list]

    logging.info(f"Processing {len(recipe_list)} recipes.")
    recipe_map = [Recipe(name, post_processors=post_processors) for name in recipe_list]

    return recipe_map


def parse_post_processors(post_processors):
    """Parsing list of post_processors"""
    logging.debug("Parsing post processors")

    post_processors_list = None

    match post_processors:
        case None:
            logging.debug("No post processors defined")
        case []:
            logging.debug("Found an empty list for post processors")
        case list():
            post_processors_list = post_processors
        case str() if post_processors.find(",") != -1:
            post_processors_list = [
                post_processor.strip()
                for post_processor in post_processors.split(",")
                if post_processor.strip()
            ]
        case str():
            post_processors_list = [
                post_processor.strip()
                for post_processor in post_processors.split(" ")
                if post_processor.strip()
            ]

    logging.info(
        f"Post Processors List: {post_processors_list}"
    ) if post_processors_list else None

    return post_processors_list


def process_recipe(recipe, disable_recipe_trust_check, args):
    if getattr(args, "dry_run", False):
        logging.info("Dry run: processing recipe %s", recipe.identifier)
        if disable_recipe_trust_check:
            logging.info(
                "Dry run: trust verification disabled for %s", recipe.identifier
            )
            recipe.verified = None
        else:
            logging.info("Dry run: would verify trust info for %s", recipe.identifier)
        logging.info("Dry run: would run recipe %s", recipe.identifier)
        logging.info(
            "Dry run: would evaluate trust update flow for %s",
            recipe.identifier,
        )
        return recipe
    if disable_recipe_trust_check:
        logging.debug("Setting Recipe verification to None")
        recipe.verified = None
    else:
        logging.debug("Checking Recipe verification")
        recipe.verify_trust_info(args)

    match recipe.verified:
        case False | None if disable_recipe_trust_check:
            logging.debug("Running Recipe without verification")
            recipe.run(args)
        case True:
            logging.debug("Running Recipe after successful verification")
            recipe.run(args)
        case False:
            # When trust verification fails we update trust info and stop
            # without running the recipe. Operators reading the log would
            # otherwise have no signal that the recipe didn't actually
            # execute — they'd just see 'Processed 0 recipes' at the end
            # and have to infer the two-phase behaviour.
            logging.info(
                "Trust verification failed for %s; updating trust info. "
                "The recipe will NOT run on this invocation — re-run the "
                "wrapper after the trust update is committed to execute it.",
                recipe.identifier,
            )
            recipe.update_trust_info(args)

    return recipe


def update_trust_only_workflow(recipe_list, args):
    """Update trust information for recipes without running them.

    This workflow:
    - Verifies trust info for each recipe
    - Updates trust info for recipes that fail verification
    - Formats updated recipe files automatically
    - Skips recipes that already pass verification
    - Does not run recipes or perform git operations

    Args:
        recipe_list: List of Recipe objects to process
        args: Parsed command-line arguments

    Returns:
        Tuple of (updated_recipes, skipped_recipes, failed_recipes)
    """
    updated_recipes = []
    skipped_recipes = []
    failed_recipes = []

    max_workers = max(1, args.concurrency)
    logging.info(
        f"Update-trust-only mode: checking {len(recipe_list)} recipes with concurrency={max_workers}"
    )

    def update_trust_for_recipe(recipe: Recipe):
        """Process a single recipe for trust update."""
        logging.info(f"Checking trust info for: {recipe.identifier}")

        if getattr(args, "dry_run", False):
            logging.info("Dry run: would verify trust info for %s", recipe.identifier)
            # Simulate verification for dry run
            logging.info(
                "Dry run: would update trust info if verification fails for %s",
                recipe.identifier,
            )
            return recipe

        # Verify trust info
        try:
            recipe.verify_trust_info(args)
        except Exception as e:
            logging.error(f"Failed to verify trust info for {recipe.identifier}: {e}")
            recipe.error = True
            return recipe

        # Update trust if verification failed
        if recipe.verified is False:
            logging.info(
                f"Trust verification failed for {recipe.identifier}, updating..."
            )
            try:
                recipe.update_trust_info(args)
                recipe.updated = True
                logging.info(f"Successfully updated trust info for {recipe.identifier}")
            except Exception as e:
                logging.error(
                    f"Failed to update trust info for {recipe.identifier}: {e}"
                )
                recipe.error = True
        elif recipe.verified is True:
            logging.debug(
                f"Trust verification passed for {recipe.identifier}, skipping"
            )
        else:
            logging.warning(
                f"Trust verification returned None for {recipe.identifier}, skipping"
            )

        return recipe

    # Process recipes concurrently
    if getattr(args, "dry_run", False):
        # Sequential processing for dry run to keep logs clean
        for r in recipe_list:
            update_trust_for_recipe(r)
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(update_trust_for_recipe, r) for r in recipe_list]
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as e:
                    logging.error(f"Unexpected error processing recipe: {e}")

    # Categorize results
    for recipe in recipe_list:
        if recipe.error:
            failed_recipes.append(recipe)
        elif recipe.updated:
            updated_recipes.append(recipe)
        else:
            skipped_recipes.append(recipe)

    # Log summary
    logging.info("\n" + "=" * 60)
    logging.info("Trust Update Summary:")
    logging.info(f"  Updated: {len(updated_recipes)} recipes")
    logging.info(f"  Skipped (already trusted): {len(skipped_recipes)} recipes")
    logging.info(f"  Failed: {len(failed_recipes)} recipes")
    logging.info("=" * 60)

    if updated_recipes:
        logging.info("\nUpdated recipes:")
        for r in updated_recipes:
            logging.info(f"  - {r.identifier}")

    if failed_recipes:
        logging.warning("\nFailed recipes:")
        for r in failed_recipes:
            logging.warning(f"  - {r.identifier}")

    return updated_recipes, skipped_recipes, failed_recipes


def main():
    args = setup_args()
    setup_logger(args.debug if args.debug else False)
    logging.info("Running autopkg_wrapper")

    override_repo_info = None

    post_processors_list = parse_post_processors(post_processors=args.post_processors)
    recipe_list = parse_recipe_list(
        recipes=args.recipes,
        recipe_file=args.recipe_file,
        post_processors=post_processors_list,
        args=args,
    )

    # Branch into trust-only workflow if --update-trust-only is set
    if getattr(args, "update_trust_only", False):
        logging.info("Update-trust-only mode enabled")
        if getattr(args, "dry_run", False):
            logging.info("Dry run enabled: no trust updates will be executed")

        updated_recipes, skipped_recipes, failed_recipes = update_trust_only_workflow(
            recipe_list=recipe_list, args=args
        )

        # Exit with appropriate code
        if failed_recipes:
            logging.error(f"Trust update failed for {len(failed_recipes)} recipes")
            sys.exit(1)
        else:
            logging.info("Trust update workflow completed successfully")
            sys.exit(0)

    failed_recipes = []

    if getattr(args, "dry_run", False):
        logging.info("Dry run enabled: no external commands will be executed")
        if args.disable_git_commands:
            logging.info("Dry run: git commands already disabled")

    # Run recipes concurrently using a thread pool to parallelize subprocess calls
    max_workers = max(1, args.concurrency)
    logging.info(f"Running recipes with concurrency={max_workers}")

    def run_one(r: Recipe):
        logging.info(f"Processing Recipe: {r.identifier}")
        if args.dry_run:
            logging.info(
                "Dry run: would process recipe %s with trust checks and run",
                r.identifier,
            )
        process_recipe(
            recipe=r,
            disable_recipe_trust_check=args.disable_recipe_trust_check,
            args=args,
        )
        # Git updates and notifications are applied serially after all recipes finish
        return r

    if args.recipe_processing_order:
        batches = build_recipe_batches(
            recipe_list=recipe_list,
            recipe_processing_order=args.recipe_processing_order,
        )
        if args.debug:
            logging.info("Recipe processing batches:")
            batch_descriptions = describe_recipe_batches(batches)
            for batch_desc in batch_descriptions:
                batch_type = batch_desc.get("type") or "unknown"
                logging.info(
                    f"Batch type={batch_type} count={batch_desc.get('count', 0)}"
                )
        else:
            batch_descriptions = describe_recipe_batches(batches)
        for batch, batch_desc in zip(batches, batch_descriptions, strict=False):
            batch_type = batch_desc.get("type") or "unknown"
            if args.debug:
                logging.info(f"Beginning {batch_type} batch")
                logging.info(f"Batch recipes: {batch_desc.get('recipes', [])}")
            if args.dry_run:
                for r in batch:
                    run_one(r)
                continue
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(run_one, r) for r in batch]
                for fut in as_completed(futures):
                    r = fut.result()
                    if r.error or r.results.get("failed"):
                        failed_recipes.append(r)
    elif recipe_list:
        if args.debug:
            logging.info("Recipe processing batches:")
            logging.info("Batch type=all count=%d", len(recipe_list))
            logging.info("Batch recipes: %s", [r.identifier for r in recipe_list])
        if args.dry_run:
            for r in recipe_list:
                run_one(r)
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(run_one, r) for r in recipe_list]
                for fut in as_completed(futures):
                    r = fut.result()
                    if r.error or r.results.get("failed"):
                        failed_recipes.append(r)

    # Apply git updates serially to avoid branch/commit conflicts when concurrency > 1
    if args.dry_run:
        logging.info("Dry run: skipping git updates")
    elif args.disable_git_commands:
        logging.info("Skipping git updates (disabled)")
    else:
        if override_repo_info is None:
            override_repo_info = get_override_repo_info(args)
        for r in recipe_list:
            update_recipe_repo(
                git_info=override_repo_info,
                recipe=r,
                disable_recipe_trust_check=args.disable_recipe_trust_check,
                args=args,
            )

    # Send notifications serially to simplify rate limiting and ordering
    if args.slack_token:
        if args.dry_run:
            logging.info("Dry run: skipping Slack notifications")
        else:
            for r in recipe_list:
                slack.send_notification(recipe=r, token=args.slack_token)

    # Optionally open a PR for updated trust information
    if args.create_pr and recipe_list:
        if args.dry_run:
            logging.info("Dry run: skipping PR creation")
        elif args.disable_git_commands:
            logging.info("Skipping PR creation (disabled git commands)")
        else:
            if override_repo_info is None:
                override_repo_info = get_override_repo_info(args)
            # Choose a representative recipe for the PR title/body
            rep_recipe = next(
                (r for r in recipe_list if r.updated is True or r.verified is False),
                recipe_list[0],
            )
            pr_url = git.create_pull_request(
                git_info=override_repo_info, recipe=rep_recipe
            )
            logging.info(f"Created Pull Request for trust info updates: {pr_url}")

    # Create GitHub issue for failed recipes
    if args.create_issues and failed_recipes and args.github_token:
        if args.dry_run:
            logging.info("Dry run: skipping issue creation")
        elif args.disable_git_commands:
            logging.info("Skipping issue creation (disabled git commands)")
        else:
            if override_repo_info is None:
                override_repo_info = get_override_repo_info(args)
            issue_url = git.create_issue_for_failed_recipes(
                git_info=override_repo_info, failed_recipes=failed_recipes
            )
            logging.info(f"Created GitHub issue for failed recipes: {issue_url}")

    # Optionally process reports after running recipes
    if getattr(args, "process_reports", False):
        if args.dry_run:
            logging.info("Dry run: skipping report processing")
            return
        repo_branch = ""
        repo_url = None
        repo_path = None
        if override_repo_info is None and not args.disable_git_commands:
            override_repo_info = get_override_repo_info(args)
        if override_repo_info is not None:
            repo_url = override_repo_info.get("override_repo_url")
            repo_path = str(override_repo_info.get("override_repo_path"))
            if not args.disable_git_commands:
                repo_branch = git.get_current_branch(override_repo_info)
        rc = process_reports(
            zip_file=args.reports_zip,
            extract_dir=args.reports_extract_dir,
            reports_dir=(args.reports_dir or "/private/tmp/autopkg"),
            environment="",
            run_date=args.reports_run_date,
            out_dir=args.reports_out_dir,
            debug=args.debug,
            strict=args.reports_strict,
            repo_url=repo_url,
            repo_branch=repo_branch,
            repo_path=repo_path,
        )
        if rc:
            sys.exit(rc)

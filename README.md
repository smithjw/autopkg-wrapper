# autopkg-wrapper

`autopkg_wrapper` is a small package that can be used to run [`autopkg`](https://github.com/autopkg/autopkg) within CI/CD environments such as GitHub Actions.

The easiest way to run it is by installing with pip.

```shell
pip install autopkg-wrapper
```

## Command Line Parameters

```shell
-h, --help                      Show this help message and exit
--recipe-file RECIPE_FILE       Path to a list of recipes to run (cannot be run with --recipes)
--recipes [RECIPES ...]         Recipes to run with autopkg (cannot be run with --recipe-file)
--recipe-processing-order [RECIPE_PROCESSING_ORDER ...]
                                Optional processing order for recipe "types" (suffix segments after the first '.'); supports partial tokens like upload/auto_update; env var AW_RECIPE_PROCESSING_ORDER expects comma-separated values
--debug                         Enable debug logging when running script
 --disable-recipe-trust-check    If this option is used, recipe trust verification will not be run prior to a recipe run.
 --github-token GITHUB_TOKEN     A token used to publish a PR to your GitHub repo if overrides require their trust to be updated
 --branch-name BRANCH_NAME       Branch name to be used where recipe overrides have failed their trust verification and need to be updated.
                                 By default, this will be in the format of "fix/update_trust_information/YYYY-MM-DDTHH-MM-SS"
 --create-pr                     If enabled, autopkg_wrapper will open a PR for updated trust information
 --create-issues                 Create a GitHub issue for recipes that fail during processing
 --disable-git-commands          If this option is used, git commands won't be run
 --post-processors [POST_PROCESSORS ...]
                                 One or more autopkg post processors to run after each recipe execution
 --autopkg-prefs AW_AUTOPKG_PREFS_FILE
                                 Path to the autopkg preferences you'd like to use
 --overrides-repo-path AUTOPKG_OVERRIDES_REPO_PATH
                                 The path on disk to the git repository containing the autopkg overrides directory. If none is provided, we will try to determine it for you.
 --concurrency CONCURRENCY       Number of recipes to run in parallel (default: 1)
 --process-reports               Process autopkg report directories or zip and emit markdown summaries (runs after recipes complete)
 --reports-zip REPORTS_ZIP       Path to an autopkg_report-*.zip to extract and process
 --reports-extract-dir REPORTS_EXTRACT_DIR
                                 Directory to extract the zip into (default: autopkg_reports_summary/reports)
 --reports-dir REPORTS_DIR       Directory of reports to process (if no zip provided). Defaults to /private/tmp/autopkg when processing after a run
 --reports-out-dir REPORTS_OUT_DIR
                                 Directory to write markdown outputs (default: autopkg_reports_summary/summary)
 --reports-run-date REPORTS_RUN_DATE
                                 Run date string to include in the summary
 --reports-strict                Exit non-zero if any errors are detected in processed reports
```

## Examples

Run recipes (serial):

```bash
autopkg_wrapper --recipes Foo.download Bar.download
```

Run 3 recipes concurrently and process reports afterward:

```bash
autopkg_wrapper \
  --recipe-file /path/to/recipe_list.txt \
  --concurrency 3 \
  --disable-git-commands \
  --process-reports \
  --reports-out-dir /tmp/autopkg_reports_summary \
  --reports-strict
```

Process a reports zip explicitly (no recipe run):

```bash
autopkg_wrapper \
  --process-reports \
  --reports-zip /path/to/autopkg_report-2026-02-02.zip \
  --reports-extract-dir /tmp/autopkg_reports \
  --reports-out-dir /tmp/autopkg_reports_summary
```

Notes:

- During recipe runs, per‑recipe plist reports are written to `/private/tmp/autopkg`.
- When `--process-reports` is supplied without `--reports-zip` or `--reports-dir`, the tool processes `/private/tmp/autopkg`.
- If `AUTOPKG_JSS_URL`, `AUTOPKG_CLIENT_ID`, and `AUTOPKG_CLIENT_SECRET` are set, uploaded package rows are enriched with Jamf package links.
  - No extra CLI flag is required; enrichment runs automatically when all three env vars are present.

An example folder structure and GitHub Actions Workflow is available within the [`actions-demo`](actions-demo)

## Credits

- [`autopkg_tools` from Facebook](https://github.com/facebook/IT-CPE/tree/main/legacy/autopkg_tools)
- [`autopkg_tools` from Facebook, modified by Gusto](https://github.com/Gusto/it-cpe-opensource/tree/main/autopkg)

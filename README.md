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
--debug                         Enable debug logging when running script
--override-trust                If set recipe override trust verification will be disabled. (Default: True)
--github-token GITHUB_TOKEN     A token used to publish a PR to your GitHub repo if overrides require their trust to be updated
--branch-name BRANCH_NAME       Branch name to be used where recipe overrides have failed their trust verification and need to be updated.
                                By default, this will be in the format of "fix/update_trust_information/YYYY-MM-DDTHH-MM-SS"
--create-pr                     If enabled, autopkg_wrapper will open a PR for updated trust information
--autopkg-overrides-repo-path AUTOPKG_OVERRIDES_REPO_PATH
                                The path on disk to the git repository containing the autopkg overrides directory. If none is provided, we will try to determine it for you.
```

## Example

An example folder structure and GitHub Actions Workflow is available within the [`actions-demo`](actions-demo)

## Credits

- [`autopkg_tools` from Facebook](https://github.com/facebook/IT-CPE/tree/main/legacy/autopkg_tools)
- [`autopkg_tools` from Facebook, modified by Gusto](https://github.com/Gusto/it-cpe-opensource/tree/main/autopkg)

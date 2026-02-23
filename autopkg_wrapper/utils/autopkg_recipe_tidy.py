#!/usr/bin/env python3
"""AutoPkg recipe YAML tidying utilities.

This module provides functionality to reformat AutoPkg recipe YAML files
for improved readability and consistency. It reorders keys, formats processors,
and adds appropriate spacing.
"""

import logging
from pathlib import Path

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.constructor import DuplicateKeyError
except ImportError as err:
    raise ImportError(
        "ruamel.yaml is required for recipe tidying. "
        "Install with: pip install ruamel.yaml"
    ) from err


def optimise_autopkg_recipes(recipe: dict) -> dict:
    """Optimize AutoPkg recipe structure for human readability.

    This function performs three optimizations:
    1. Adjusts Processor dictionaries so Comment and Arguments keys are
       moved to the end, ensuring the Processor key is first.
    2. Ensures the NAME key is the first item in the Input dictionary.
    3. Orders the items so that Input and Process dictionaries are at the end.

    Args:
        recipe: The recipe dictionary to optimize

    Returns:
        A dict with optimized key ordering
    """
    # Convert to regular dict to avoid OrderedDict issues
    recipe = dict(recipe)

    if "Process" in recipe:
        process = recipe["Process"]
        new_process = []
        for processor in process:
            processor = dict(processor)
            # Reorder processor keys: Processor first, then others, Comment and Arguments last
            keys = list(processor.keys())
            ordered_keys = []

            # Processor key first
            if "Processor" in keys:
                ordered_keys.append("Processor")

            # Other keys (excluding Processor, Comment, Arguments)
            for key in keys:
                if key not in ["Processor", "Comment", "Arguments"]:
                    ordered_keys.append(key)

            # Comment and Arguments last
            if "Comment" in keys:
                ordered_keys.append("Comment")
            if "Arguments" in keys:
                ordered_keys.append("Arguments")

            new_processor = {k: processor[k] for k in ordered_keys}
            new_process.append(new_processor)
        recipe["Process"] = new_process

    if "Input" in recipe:
        input_dict = dict(recipe["Input"])
        # Reorder Input keys: NAME and SOFTWARE_TITLE first, then others
        keys = list(input_dict.keys())
        ordered_keys = []

        if "NAME" in keys:
            ordered_keys.append("NAME")
        if "SOFTWARE_TITLE" in keys:
            ordered_keys.append("SOFTWARE_TITLE")

        for key in keys:
            if key not in ["NAME", "SOFTWARE_TITLE"]:
                ordered_keys.append(key)

        recipe["Input"] = {k: input_dict[k] for k in ordered_keys}

    desired_order = [
        "Comment",
        "Description",
        "Identifier",
        "ParentRecipe",
        "MinimumVersion",
        "Input",
        "Process",
        "ParentRecipeTrustInfo",
    ]
    desired_list = [k for k in desired_order if k in recipe]
    reordered_recipe = {k: recipe[k] for k in desired_list}
    return reordered_recipe


def format_autopkg_recipes(output: str) -> str:
    """Add lines between Input and Process, and between multiple processes.

    This aids readability of YAML recipes by adding blank lines in strategic places.

    Args:
        output: The YAML string to format

    Returns:
        Formatted YAML string with improved spacing
    """
    # Add line before specific processors
    for item in ["Input:", "Process:", "- Processor:", "ParentRecipeTrustInfo:"]:
        output = output.replace(item, "\n" + item)

    # Remove line before first process
    output = output.replace("Process:\n\n-", "Process:\n-")

    recipe = []
    lines = output.splitlines()
    for line in lines:
        # Convert quoted strings with newlines in them to scalars
        if "\\n" in line:
            spaces = len(line) - len(line.lstrip()) + 2
            space = " "
            line = line.replace(': "', f": |\n{space * spaces}")
            line = line.replace("\\t", "    ")
            line = line.replace('\\n"', "")
            line = line.replace("\\n", f"\n{space * spaces}")
            line = line.replace('\\"', '"')
            if line[-1] == '"':
                line = line[:-1]

        recipe.append(line)
    recipe.append("")
    return "\n".join(recipe)


def convert_to_yaml(recipe_dict: dict) -> str:
    """Convert recipe dictionary to YAML string.

    Args:
        recipe_dict: The recipe dictionary to convert

    Returns:
        YAML string representation
    """
    from io import StringIO

    yaml = YAML()
    yaml.default_flow_style = False
    yaml.width = 4096  # Large width to prevent wrapping
    yaml.preserve_quotes = True
    yaml.map_indent = 2
    yaml.sequence_indent = 2
    yaml.sequence_dash_offset = 0

    # Explicitly represent None as 'null' instead of empty
    yaml.representer.add_representer(
        type(None),
        lambda dumper, value: dumper.represent_scalar("tag:yaml.org,2002:null", "null"),
    )

    stream = StringIO()
    yaml.dump(recipe_dict, stream)
    return stream.getvalue()


def tidy_yaml_recipe(in_path: Path | str, out_path: Path | str | None = None) -> bool:
    """Tidy up AutoPkg YAML recipe file.

    Args:
        in_path: Path to input YAML file
        out_path: Path to output file (if None, overwrites input file)

    Returns:
        True if successful, False otherwise
    """
    in_path = Path(in_path)
    out_path = in_path if out_path is None else Path(out_path)

    if not str(in_path).endswith(".yaml"):
        logging.debug(f"Not processing {in_path} (not a .yaml file)")
        return False

    try:
        with open(in_path) as in_file:
            yaml = YAML()
            yaml.preserve_quotes = True
            input_data = yaml.load(in_file)
    except FileNotFoundError:
        logging.error(f"ERROR: {in_path} not found")
        return False
    except DuplicateKeyError:
        logging.error(f"ERROR: Duplicate key found in {in_path}")
        return False
    except Exception as e:
        logging.error(f"ERROR: Failed to load {in_path}: {e}")
        return False

    # Handle conversion of AutoPkg recipes
    if str(in_path).endswith(".recipe.yaml"):
        input_data = optimise_autopkg_recipes(input_data)
        output = convert_to_yaml(input_data)
        output = format_autopkg_recipes(output)
    else:
        output = convert_to_yaml(input_data)

    try:
        with open(out_path, "w", encoding="utf-8") as out_file:
            out_file.write(output)
        logging.debug(f"Tidied recipe: {out_path}")
        return True
    except OSError:
        logging.error(f"ERROR: could not write to {out_path}")
        return False

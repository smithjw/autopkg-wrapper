import logging


def order_recipe_list(recipe_list, order):
    # This option comes in handy if you include additional recipe type names in your overrides and wish them to be processed in a specific order.
    # We'll specifically look for these recipe types after the first period (.) in the recipe name.
    # For example, if you have the following recipes to be processed:
    #     ExampleApp.auto_install.jamf
    #     ExampleApp.upload.jamf
    #     ExampleApp.self_service.jamf
    # And you want to ensure that the .upload recipes are always processed first, followed by .auto_install, and finally .self_service, you would provide the following processing order:
    #     `--recipe-processing-order upload.jamf auto_install.jamf self_service.jamf`
    # This would ensure that all .upload recipes are processed before any other recipe types.
    # Within each recipe type, the recipes will be ordered alphabetically.
    # We assume that no extensions are provided (but will strip them if needed - extensions that are stripped include .recipe or .recipe.yaml).

    def strip_known_extensions(value: str) -> str:
        value = value.strip()
        if value.endswith(".recipe.yaml"):
            return value[: -len(".recipe.yaml")]
        if value.endswith(".recipe"):
            return value[: -len(".recipe")]
        return value

    def normalise_processing_order(value):
        if not value:
            return []

        items: list[str] = []
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            # String values generally come from env var defaults; treat as comma-separated.
            items = [v.strip() for v in raw.split(",")]
        else:
            # argparse typically provides a list here, but env var defaults can leak through.
            for v in value:
                if v is None:
                    continue
                v = str(v).strip()
                if not v:
                    continue
                if "," in v:
                    items.extend([p.strip() for p in v.split(",")])
                else:
                    items.append(v)

        normalised: list[str] = []
        seen: set[str] = set()
        for item in items:
            if not item:
                continue
            item = item.lstrip(".")
            item = strip_known_extensions(item)
            if not item or item in seen:
                continue
            seen.add(item)
            normalised.append(item)
        return normalised

    def recipe_type(recipe_name: str) -> str:
        # Type is everything after the first '.' (e.g. Example.upload.jamf -> upload.jamf)
        parts = recipe_name.split(".", 1)
        return parts[1] if len(parts) == 2 else ""

    def recipe_segments_after_first_dot(recipe_name: str) -> list[str]:
        after_first = recipe_type(recipe_name)
        return [p for p in after_first.split(".") if p] if after_first else []

    def pattern_matches_segments(pattern: str, segments: list[str]) -> bool:
        # Pattern can be a single token ("auto_update") or a dot-separated sequence
        # ("upload.jamf", "auto_update.jamf", etc.).
        if not pattern:
            return False
        pattern_parts = [p for p in pattern.split(".") if p]
        if not pattern_parts:
            return False

        # Case-insensitive matching.
        segments_norm = [s.casefold() for s in segments]
        pattern_parts_norm = [p.casefold() for p in pattern_parts]

        if len(pattern_parts_norm) == 1:
            return pattern_parts_norm[0] in segments_norm

        # Contiguous subsequence match.
        for start in range(0, len(segments_norm) - len(pattern_parts_norm) + 1):
            if (
                segments_norm[start : start + len(pattern_parts_norm)]
                == pattern_parts_norm
            ):
                return True
        return False

    if not recipe_list:
        return recipe_list

    normalised_order = normalise_processing_order(order)

    # If the provided order contains no usable tokens, do not re-order.
    # (We still strip known extensions, which is order-preserving.)
    if not normalised_order:
        return [
            strip_known_extensions(str(r).strip()) for r in recipe_list if r is not None
        ]

    # First, normalise recipe names by stripping known extensions.
    normalised_recipes: list[str] = []
    for r in recipe_list:
        if r is None:
            continue
        normalised_recipes.append(strip_known_extensions(str(r).strip()))

    # If a processing order is supplied, match each recipe to the *first* pattern it satisfies.
    # This supports both direct matches ("upload.jamf") and partial matches ("upload",
    # "auto_update") against dot-separated segments after the first '.' in the recipe name.
    pattern_groups: dict[str, list[str]] = {p: [] for p in normalised_order}
    unmatched: list[str] = []

    for r in normalised_recipes:
        segments = recipe_segments_after_first_dot(r)
        matched = False
        for p in normalised_order:
            if pattern_matches_segments(p, segments):
                pattern_groups[p].append(r)
                matched = True
                break
        if not matched:
            unmatched.append(r)

    ordered: list[str] = []
    for p in normalised_order:
        ordered.extend(sorted(pattern_groups[p], key=str.casefold))

    # Remaining recipes: group by their full type string and order groups alphabetically,
    # with empty-type last.
    groups: dict[str, list[str]] = {}
    for r in unmatched:
        t = recipe_type(r)
        groups.setdefault(t, []).append(r)

    for t in sorted(groups.keys(), key=lambda x: (x == "", x.casefold())):
        ordered.extend(sorted(groups[t], key=str.casefold))

    logging.debug(f"Recipe processing order: {normalised_order}")
    logging.debug(f"Ordered recipes: {ordered}")

    return ordered

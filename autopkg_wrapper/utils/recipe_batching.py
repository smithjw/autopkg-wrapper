from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol


class HasName(Protocol):
    """Protocol for objects that have a name attribute (recipe name without extension)."""

    name: str


def recipe_type_for(recipe: HasName) -> str:
    """Extract the recipe type from the recipe name.

    Args:
        recipe: Recipe object with a name attribute

    Returns:
        str: Recipe type (e.g., "upload.jamf" from "Firefox.upload.jamf")
    """
    parts = recipe.name.split(".", 1)
    return parts[1] if len(parts) == 2 else ""


def recipe_identifier_for(recipe: HasName) -> str:
    """Get the recipe identifier for display purposes.

    Args:
        recipe: Recipe object

    Returns:
        str: Recipe identifier (falls back to name if identifier not available)
    """
    identifier = getattr(recipe, "identifier", None)
    return identifier if identifier else recipe.name


def build_recipe_batches[T: HasName](
    recipe_list: Iterable[T], recipe_processing_order
) -> list[list[T]]:
    recipe_list = list(recipe_list)
    if not recipe_list:
        return []
    if not recipe_processing_order:
        return [recipe_list]

    batches: list[list[T]] = []
    current_batch: list[T] = []
    current_type = None
    for recipe in recipe_list:
        r_type = recipe_type_for(recipe)
        if current_type is None or r_type == current_type:
            current_batch.append(recipe)
            current_type = r_type
            continue
        batches.append(current_batch)
        current_batch = [recipe]
        current_type = r_type
    if current_batch:
        batches.append(current_batch)
    return batches


def describe_recipe_batches[T: HasName](
    batches: Iterable[Iterable[T]],
) -> list[dict[str, object]]:
    return [
        {
            "type": (recipe_type_for(batch_list[0]) if batch_list else ""),
            "count": len(batch_list),
            "recipes": [recipe_identifier_for(r) for r in batch_list],
        }
        for batch in batches
        if (batch_list := list(batch)) is not None
    ]

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol


class HasFilename(Protocol):
    filename: str


def recipe_type_for(recipe: HasFilename) -> str:
    parts = recipe.filename.split(".", 1)
    return parts[1] if len(parts) == 2 else ""


def recipe_identifier_for(recipe: HasFilename) -> str:
    identifier = getattr(recipe, "identifier", None)
    return identifier if identifier else recipe.filename


def build_recipe_batches[T: HasFilename](
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


def describe_recipe_batches[T: HasFilename](
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

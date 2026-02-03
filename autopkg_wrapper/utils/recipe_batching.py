from __future__ import annotations

from typing import Iterable, Protocol, TypeVar


class HasFilename(Protocol):
    filename: str


T = TypeVar("T", bound=HasFilename)


def recipe_type_for(recipe: HasFilename) -> str:
    parts = recipe.filename.split(".", 1)
    return parts[1] if len(parts) == 2 else ""


def recipe_identifier_for(recipe: HasFilename) -> str:
    identifier = getattr(recipe, "identifier", None)
    return identifier if identifier else recipe.filename


def build_recipe_batches(
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


def describe_recipe_batches(batches: Iterable[Iterable[T]]) -> list[dict[str, object]]:
    descriptions: list[dict[str, object]] = []
    for batch in batches:
        batch_list = list(batch)
        batch_type = recipe_type_for(batch_list[0]) if batch_list else ""
        identifiers = [recipe_identifier_for(r) for r in batch_list]
        descriptions.append(
            {"type": batch_type, "count": len(batch_list), "recipes": identifiers}
        )
    return descriptions

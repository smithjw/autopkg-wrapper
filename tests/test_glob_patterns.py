"""Tests for glob pattern detection and recipe discovery."""

import tempfile
from pathlib import Path
from types import SimpleNamespace

from autopkg_wrapper.autopkg_wrapper import (
    discover_recipes_from_glob,
    has_glob_pattern,
    normalize_recipe_identifier,
    parse_recipe_list,
)


class TestNormalizeRecipeIdentifier:
    """Test recipe identifier normalization."""

    def test_normalizes_recipe_yaml_path(self):
        result = normalize_recipe_identifier(
            "overrides/Firefox/Firefox.upload.jamf.recipe.yaml"
        )
        assert result == "Firefox.upload.jamf"

    def test_normalizes_recipe_plist_path(self):
        result = normalize_recipe_identifier(
            "overrides/Chrome/Chrome.download.recipe.plist"
        )
        assert result == "Chrome.download"

    def test_normalizes_recipe_path(self):
        result = normalize_recipe_identifier("path/to/Safari.pkg.recipe")
        assert result == "Safari.pkg"

    def test_normalizes_absolute_path(self):
        result = normalize_recipe_identifier(
            "/Users/test/overrides/Edge.upload.jamf.recipe.yaml"
        )
        assert result == "Edge.upload.jamf"

    def test_preserves_plain_identifier(self):
        result = normalize_recipe_identifier("Firefox.upload.jamf")
        assert result == "Firefox.upload.jamf"

    def test_handles_identifier_with_dots(self):
        result = normalize_recipe_identifier("App.with.dots.upload.jamf")
        assert result == "App.with.dots.upload.jamf"

    def test_strips_only_known_extensions(self):
        # If it doesn't match known extensions, keep as-is
        result = normalize_recipe_identifier("Firefox.somethingelse")
        assert result == "Firefox.somethingelse"


class TestHasGlobPattern:
    """Test glob pattern detection."""

    def test_detects_asterisk(self):
        assert has_glob_pattern("*.recipe.yaml") is True

    def test_detects_double_asterisk(self):
        assert has_glob_pattern("**/*.recipe.yaml") is True

    def test_detects_question_mark(self):
        assert has_glob_pattern("recipe?.yaml") is True

    def test_detects_brackets(self):
        assert has_glob_pattern("recipe[0-9].yaml") is True

    def test_no_pattern_returns_false(self):
        assert has_glob_pattern("recipe.yaml") is False

    def test_empty_string_returns_false(self):
        assert has_glob_pattern("") is False


class TestDiscoverRecipesFromGlob:
    """Test recipe discovery from glob patterns."""

    def test_discovers_recipes_with_yaml_extension(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create test recipe files
            (tmppath / "Firefox.recipe.yaml").touch()
            (tmppath / "Chrome.recipe.yaml").touch()

            # Discover recipes
            pattern = str(tmppath / "*.recipe.yaml")
            recipes = discover_recipes_from_glob(pattern)

            # Should find both recipes
            assert len(recipes) == 2
            assert "Firefox" in recipes
            assert "Chrome" in recipes

    def test_discovers_recipes_with_plist_extension(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create test recipe files
            (tmppath / "Firefox.recipe.plist").touch()
            (tmppath / "Chrome.recipe.plist").touch()

            # Discover recipes
            pattern = str(tmppath / "*.recipe.plist")
            recipes = discover_recipes_from_glob(pattern)

            # Should find both recipes
            assert len(recipes) == 2
            assert "Firefox" in recipes
            assert "Chrome" in recipes

    def test_discovers_recipes_with_recipe_extension(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create test recipe files
            (tmppath / "Firefox.recipe").touch()
            (tmppath / "Chrome.recipe").touch()

            # Discover recipes
            pattern = str(tmppath / "*.recipe")
            recipes = discover_recipes_from_glob(pattern)

            # Should find both recipes
            assert len(recipes) == 2
            assert "Firefox" in recipes
            assert "Chrome" in recipes

    def test_discovers_recipes_recursively(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create nested directories with recipe files
            (tmppath / "group1").mkdir()
            (tmppath / "group2").mkdir()
            (tmppath / "group1" / "Firefox.upload.jamf.recipe.yaml").touch()
            (tmppath / "group2" / "Chrome.download.recipe.yaml").touch()

            # Discover recipes recursively
            pattern = str(tmppath / "**/*.recipe.yaml")
            recipes = discover_recipes_from_glob(pattern)

            # Should find both recipes
            assert len(recipes) == 2
            assert "Firefox.upload.jamf" in recipes
            assert "Chrome.download" in recipes

    def test_returns_empty_list_for_no_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # No recipe files exist
            pattern = str(tmppath / "*.recipe.yaml")
            recipes = discover_recipes_from_glob(pattern)

            assert recipes == []

    def test_strips_recipe_extensions_correctly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create recipe with complex naming
            (tmppath / "Firefox.upload.jamf.recipe.yaml").touch()

            # Discover recipes
            pattern = str(tmppath / "*.recipe.yaml")
            recipes = discover_recipes_from_glob(pattern)

            # Should strip .recipe.yaml but keep the rest
            assert recipes == ["Firefox.upload.jamf"]


class TestParseRecipeListWithGlob:
    """Test parse_recipe_list with glob patterns."""

    def test_parses_single_glob_pattern_string(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create test recipe files
            (tmppath / "Firefox.recipe.yaml").touch()
            (tmppath / "Chrome.recipe.yaml").touch()

            # Parse with glob pattern
            args = SimpleNamespace(recipe_processing_order=None)
            pattern = str(tmppath / "*.recipe.yaml")
            recipe_map = parse_recipe_list(
                recipes=pattern,
                recipe_file=None,
                post_processors=None,
                args=args,
            )

            # Should create Recipe objects for discovered files
            assert len(recipe_map) == 2
            identifiers = [r.identifier for r in recipe_map]
            assert "Firefox" in identifiers
            assert "Chrome" in identifiers

    def test_parses_glob_pattern_in_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create test recipe files
            (tmppath / "Firefox.recipe.yaml").touch()
            (tmppath / "Chrome.recipe.yaml").touch()

            # Parse with glob pattern in list
            args = SimpleNamespace(recipe_processing_order=None)
            pattern = str(tmppath / "*.recipe.yaml")
            recipe_map = parse_recipe_list(
                recipes=[pattern],
                recipe_file=None,
                post_processors=None,
                args=args,
            )

            # Should create Recipe objects for discovered files
            assert len(recipe_map) == 2
            identifiers = [r.identifier for r in recipe_map]
            assert "Firefox" in identifiers
            assert "Chrome" in identifiers

    def test_combines_glob_and_explicit_recipes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create test recipe files
            (tmppath / "Firefox.recipe.yaml").touch()
            (tmppath / "Chrome.recipe.yaml").touch()

            # Parse with both explicit and glob patterns
            args = SimpleNamespace(recipe_processing_order=None)
            pattern = str(tmppath / "*.recipe.yaml")
            recipe_map = parse_recipe_list(
                recipes=["ExplicitRecipe.download", pattern],
                recipe_file=None,
                post_processors=None,
                args=args,
            )

            # Should have explicit recipe plus discovered recipes
            assert len(recipe_map) == 3
            identifiers = [r.identifier for r in recipe_map]
            assert "ExplicitRecipe.download" in identifiers
            assert "Firefox" in identifiers
            assert "Chrome" in identifiers

    def test_handles_non_glob_patterns_normally(self):
        args = SimpleNamespace(recipe_processing_order=None)
        recipe_map = parse_recipe_list(
            recipes=["Firefox.download", "Chrome.download"],
            recipe_file=None,
            post_processors=None,
            args=args,
        )

        # Should work normally without glob processing
        assert len(recipe_map) == 2
        assert [r.identifier for r in recipe_map] == [
            "Firefox.download",
            "Chrome.download",
        ]

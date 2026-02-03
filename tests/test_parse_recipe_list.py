from pathlib import Path
from types import SimpleNamespace

import pytest

from autopkg_wrapper.autopkg_wrapper import parse_post_processors, parse_recipe_list


class TestParsePostProcessors:
    def test_parse_post_processors_none_and_empty(self):
        assert parse_post_processors(None) is None
        assert parse_post_processors([]) is None

    def test_parse_post_processors_list(self):
        assert parse_post_processors(["A", "B"]) == ["A", "B"]

    def test_parse_post_processors_comma_string(self):
        assert parse_post_processors("A,B") == ["A", "B"]

    def test_parse_post_processors_space_string(self):
        assert parse_post_processors("A B") == ["A", "B"]


class TestParseRecipeList:
    def _fixture_path(self, name: str) -> Path:
        return Path(__file__).resolve().parent / name

    def test_recipe_file_json(self):
        args = SimpleNamespace(recipe_processing_order=None)
        recipe_map = parse_recipe_list(
            recipes=None,
            recipe_file=self._fixture_path("recipe_list.json"),
            post_processors=None,
            args=args,
        )
        assert [r.filename for r in recipe_map] == [
            "Google_Chrome.download",
            "Microsoft_Edge.download",
            "Mozilla_Firefox.download",
        ]

    def test_recipe_file_txt(self):
        args = SimpleNamespace(recipe_processing_order=None)
        recipe_map = parse_recipe_list(
            recipes=None,
            recipe_file=self._fixture_path("recipe_list.txt"),
            post_processors=None,
            args=args,
        )
        assert [r.filename for r in recipe_map] == [
            "Google_Chrome.download",
            "Microsoft_Edge.download",
            "Mozilla_Firefox.download",
        ]

    def test_recipe_file_yaml(self):
        args = SimpleNamespace(recipe_processing_order=None)
        recipe_map = parse_recipe_list(
            recipes=None,
            recipe_file=self._fixture_path("recipe_list.yaml"),
            post_processors=None,
            args=args,
        )
        assert [r.filename for r in recipe_map] == [
            "Google_Chrome.download",
            "Microsoft_Edge.download",
            "Mozilla_Firefox.download",
        ]

    def test_recipes_string_comma(self):
        args = SimpleNamespace(recipe_processing_order=None)
        recipe_map = parse_recipe_list(
            recipes="A.download,B.download",
            recipe_file=None,
            post_processors=None,
            args=args,
        )
        assert [r.filename for r in recipe_map] == ["A.download", "B.download"]

    def test_recipes_string_space(self):
        args = SimpleNamespace(recipe_processing_order=None)
        recipe_map = parse_recipe_list(
            recipes="A.download B.download",
            recipe_file=None,
            post_processors=None,
            args=args,
        )
        assert [r.filename for r in recipe_map] == ["A.download", "B.download"]

    def test_recipes_reorders_when_order_present(self):
        args = SimpleNamespace(recipe_processing_order=["upload", "auto_install"])
        recipe_map = parse_recipe_list(
            recipes=["Foo.auto_install.jamf", "Foo.upload.jamf"],
            recipe_file=None,
            post_processors=None,
            args=args,
        )
        assert [r.filename for r in recipe_map] == [
            "Foo.upload.jamf",
            "Foo.auto_install.jamf",
        ]

    def test_recipes_reorders_and_logs_processing_count(self, caplog):
        args = SimpleNamespace(recipe_processing_order=["upload", "auto_install"])
        with caplog.at_level("INFO"):
            recipe_map = parse_recipe_list(
                recipes=["Foo.auto_install.jamf", "Foo.upload.jamf"],
                recipe_file=None,
                post_processors=None,
                args=args,
            )
        assert [r.filename for r in recipe_map] == [
            "Foo.upload.jamf",
            "Foo.auto_install.jamf",
        ]
        assert "Processing 2 recipes." in caplog.text

    def test_missing_recipes_raises_system_exit(self):
        args = SimpleNamespace(recipe_processing_order=None)
        with pytest.raises(SystemExit):
            parse_recipe_list(
                recipes=None, recipe_file=None, post_processors=None, args=args
            )

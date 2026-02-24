"""Tests for update-trust-only workflow."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from autopkg_wrapper.autopkg_wrapper import update_trust_only_workflow
from autopkg_wrapper.models.recipe import Recipe


class TestUpdateTrustOnlyWorkflow:
    """Test the update_trust_only_workflow function."""

    def test_updates_recipes_with_failed_verification(self):
        """Test that recipes with failed verification are updated."""
        # Create test recipes
        recipe1 = Recipe("Firefox.upload.jamf")
        recipe2 = Recipe("Chrome.upload.jamf")

        # Mock the verify and update methods
        recipe1.verify_trust_info = MagicMock(
            side_effect=lambda args: setattr(recipe1, "verified", False)
        )
        recipe1.update_trust_info = MagicMock()
        recipe2.verify_trust_info = MagicMock(
            side_effect=lambda args: setattr(recipe2, "verified", False)
        )
        recipe2.update_trust_info = MagicMock()

        # Create args
        args = SimpleNamespace(concurrency=1, dry_run=False)

        # Run workflow
        updated, skipped, failed = update_trust_only_workflow(
            recipe_list=[recipe1, recipe2], args=args
        )

        # Both recipes should be updated
        assert len(updated) == 2
        assert len(skipped) == 0
        assert len(failed) == 0

        # Verify methods were called
        recipe1.verify_trust_info.assert_called_once()
        recipe1.update_trust_info.assert_called_once()
        recipe2.verify_trust_info.assert_called_once()
        recipe2.update_trust_info.assert_called_once()

        # Check that updated flag is set
        assert recipe1.updated is True
        assert recipe2.updated is True

    def test_skips_recipes_with_successful_verification(self):
        """Test that recipes with successful verification are skipped."""
        # Create test recipes
        recipe1 = Recipe("Firefox.upload.jamf")
        recipe2 = Recipe("Chrome.upload.jamf")

        # Mock the verify methods - both pass
        recipe1.verify_trust_info = MagicMock(
            side_effect=lambda args: setattr(recipe1, "verified", True)
        )
        recipe1.update_trust_info = MagicMock()
        recipe2.verify_trust_info = MagicMock(
            side_effect=lambda args: setattr(recipe2, "verified", True)
        )
        recipe2.update_trust_info = MagicMock()

        # Create args
        args = SimpleNamespace(concurrency=1, dry_run=False)

        # Run workflow
        updated, skipped, failed = update_trust_only_workflow(
            recipe_list=[recipe1, recipe2], args=args
        )

        # Both recipes should be skipped
        assert len(updated) == 0
        assert len(skipped) == 2
        assert len(failed) == 0

        # Verify methods were called/not called
        recipe1.verify_trust_info.assert_called_once()
        recipe1.update_trust_info.assert_not_called()
        recipe2.verify_trust_info.assert_called_once()
        recipe2.update_trust_info.assert_not_called()

    def test_handles_mixed_verification_results(self):
        """Test handling of mixed verification results."""
        # Create test recipes
        recipe1 = Recipe("Firefox.upload.jamf")  # Will fail
        recipe2 = Recipe("Chrome.upload.jamf")  # Will pass

        # Mock the verify methods
        recipe1.verify_trust_info = MagicMock(
            side_effect=lambda args: setattr(recipe1, "verified", False)
        )
        recipe1.update_trust_info = MagicMock()
        recipe2.verify_trust_info = MagicMock(
            side_effect=lambda args: setattr(recipe2, "verified", True)
        )
        recipe2.update_trust_info = MagicMock()

        # Create args
        args = SimpleNamespace(concurrency=1, dry_run=False)

        # Run workflow
        updated, skipped, failed = update_trust_only_workflow(
            recipe_list=[recipe1, recipe2], args=args
        )

        # One updated, one skipped
        assert len(updated) == 1
        assert len(skipped) == 1
        assert len(failed) == 0

        # Check correct recipes in each list
        assert recipe1 in updated
        assert recipe2 in skipped

    def test_handles_update_failures(self):
        """Test handling of failures during trust update."""
        # Create test recipe
        recipe = Recipe("Firefox.upload.jamf")

        # Mock verify to fail and update to raise exception
        recipe.verify_trust_info = MagicMock(
            side_effect=lambda args: setattr(recipe, "verified", False)
        )
        recipe.update_trust_info = MagicMock(side_effect=Exception("Update failed"))

        # Create args
        args = SimpleNamespace(concurrency=1, dry_run=False)

        # Run workflow
        updated, skipped, failed = update_trust_only_workflow(
            recipe_list=[recipe], args=args
        )

        # Recipe should be in failed list
        assert len(updated) == 0
        assert len(skipped) == 0
        assert len(failed) == 1
        assert recipe in failed
        assert recipe.error is True

    def test_handles_verification_failures(self):
        """Test handling of failures during verification."""
        # Create test recipe
        recipe = Recipe("Firefox.upload.jamf")

        # Mock verify to raise exception
        recipe.verify_trust_info = MagicMock(
            side_effect=Exception("Verification failed")
        )
        recipe.update_trust_info = MagicMock()

        # Create args
        args = SimpleNamespace(concurrency=1, dry_run=False)

        # Run workflow
        updated, skipped, failed = update_trust_only_workflow(
            recipe_list=[recipe], args=args
        )

        # Recipe should be in failed list
        assert len(updated) == 0
        assert len(skipped) == 0
        assert len(failed) == 1
        assert recipe in failed
        assert recipe.error is True
        # Update should not be called if verify fails
        recipe.update_trust_info.assert_not_called()

    def test_dry_run_mode(self):
        """Test that dry run mode doesn't execute commands."""
        # Create test recipes
        recipe1 = Recipe("Firefox.upload.jamf")
        recipe2 = Recipe("Chrome.upload.jamf")

        # Mock methods (shouldn't be called in dry run)
        recipe1.verify_trust_info = MagicMock()
        recipe1.update_trust_info = MagicMock()
        recipe2.verify_trust_info = MagicMock()
        recipe2.update_trust_info = MagicMock()

        # Create args with dry_run enabled
        args = SimpleNamespace(concurrency=1, dry_run=True)

        # Run workflow
        updated, skipped, failed = update_trust_only_workflow(
            recipe_list=[recipe1, recipe2], args=args
        )

        # In dry run, methods should not be called
        recipe1.verify_trust_info.assert_not_called()
        recipe1.update_trust_info.assert_not_called()
        recipe2.verify_trust_info.assert_not_called()
        recipe2.update_trust_info.assert_not_called()

        # All should be skipped (not updated or failed)
        assert len(updated) == 0
        assert len(skipped) == 2
        assert len(failed) == 0

    def test_respects_concurrency_setting(self):
        """Test that concurrency setting is respected."""
        # Create multiple recipes
        recipes = [Recipe(f"Recipe{i}.upload.jamf") for i in range(5)]

        # Mock methods
        for recipe in recipes:
            recipe.verify_trust_info = MagicMock(
                side_effect=lambda args, r=recipe: setattr(r, "verified", True)
            )
            recipe.update_trust_info = MagicMock()

        # Test with different concurrency values
        args = SimpleNamespace(concurrency=3, dry_run=False)

        # Run workflow (just verify it doesn't crash with concurrency > 1)
        updated, skipped, failed = update_trust_only_workflow(
            recipe_list=recipes, args=args
        )

        # All should be processed
        assert len(updated) + len(skipped) + len(failed) == 5

    def test_empty_recipe_list(self):
        """Test handling of empty recipe list."""
        args = SimpleNamespace(concurrency=1, dry_run=False)

        # Run workflow with empty list
        updated, skipped, failed = update_trust_only_workflow(recipe_list=[], args=args)

        # All lists should be empty
        assert len(updated) == 0
        assert len(skipped) == 0
        assert len(failed) == 0

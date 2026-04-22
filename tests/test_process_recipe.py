"""Tests for the process_recipe dispatch function.

The match-statement in process_recipe picks one of three paths based on
`recipe.verified`:
 - True -> run the recipe
 - False + disable_recipe_trust_check -> run without verification
 - False -> update trust info and stop (does NOT run)

The third path is the one that historically caused the most operator
confusion: the wrapper quietly updates trust info, returns, and the
caller reports 'Processed 0 recipes' at the end with no hint that the
recipe didn't execute. The tests below pin the INFO log added to that
branch so the behaviour doesn't regress.
"""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

from autopkg_wrapper.autopkg_wrapper import process_recipe
from autopkg_wrapper.models.recipe import Recipe


def _args(**overrides) -> SimpleNamespace:
    """Minimal args object. Override fields as needed per test."""
    base = {
        "debug": False,
        "dry_run": False,
        "disable_git_commands": True,
        "disable_recipe_trust_check": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestProcessRecipeTrustFailurePath:
    """When trust verification fails, the wrapper updates trust and STOPS.

    This is by design — the updated trust info needs to be committed and
    the wrapper re-invoked before the recipe actually runs. Operators
    have to be told, loudly, that their recipe is NOT running on this
    invocation.
    """

    def test_logs_explicit_skip_on_trust_failure(self, caplog):
        recipe = Recipe("Firefox.upload.jamf")
        recipe.verify_trust_info = MagicMock(
            side_effect=lambda args: setattr(recipe, "verified", False)
        )
        recipe.update_trust_info = MagicMock()
        recipe.run = MagicMock()

        with caplog.at_level(logging.INFO):
            process_recipe(
                recipe=recipe,
                disable_recipe_trust_check=False,
                args=_args(),
            )

        # update_trust_info is called; run is NOT
        recipe.update_trust_info.assert_called_once()
        recipe.run.assert_not_called()

        # The critical behavioural signal: an operator-visible INFO log
        # explaining that the recipe did not run.
        messages = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
        assert any("Trust verification failed" in m for m in messages), (
            f"expected 'Trust verification failed' INFO, got: {messages}"
        )
        assert any("will NOT run on this invocation" in m for m in messages), (
            f"expected 'will NOT run' wording, got: {messages}"
        )
        # Recipe identifier should be in the message so grepping a log
        # with many recipes surfaces the specific one that didn't run.
        assert any("Firefox.upload.jamf" in m for m in messages)

    def test_successful_verification_runs_recipe_without_skip_log(self, caplog):
        recipe = Recipe("Firefox.upload.jamf")
        recipe.verify_trust_info = MagicMock(
            side_effect=lambda args: setattr(recipe, "verified", True)
        )
        recipe.update_trust_info = MagicMock()
        recipe.run = MagicMock()

        with caplog.at_level(logging.INFO):
            process_recipe(
                recipe=recipe,
                disable_recipe_trust_check=False,
                args=_args(),
            )

        recipe.run.assert_called_once()
        recipe.update_trust_info.assert_not_called()

        messages = [r.getMessage() for r in caplog.records]
        # The skip-log must NOT appear on the happy path.
        assert not any("Trust verification failed" in m for m in messages)
        assert not any("will NOT run on this invocation" in m for m in messages)

    def test_trust_check_disabled_runs_without_skip_log(self, caplog):
        recipe = Recipe("Firefox.upload.jamf")
        recipe.verify_trust_info = MagicMock()
        recipe.update_trust_info = MagicMock()
        recipe.run = MagicMock()

        with caplog.at_level(logging.INFO):
            process_recipe(
                recipe=recipe,
                disable_recipe_trust_check=True,
                args=_args(),
            )

        # verify_trust_info is skipped entirely when trust-check is
        # disabled; the recipe runs unconditionally.
        recipe.verify_trust_info.assert_not_called()
        recipe.run.assert_called_once()
        recipe.update_trust_info.assert_not_called()

        messages = [r.getMessage() for r in caplog.records]
        assert not any("will NOT run on this invocation" in m for m in messages)

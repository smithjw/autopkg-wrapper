"""Tests for the _needs_git_updates helper.

Pin the predicate that gates whether the 'Skipping git updates (disabled)'
log fires. A clean run — every recipe ran successfully, no trust updates,
no committable changes — must register as "nothing to do" so we don't
emit a misleading skip-log.
"""

from autopkg_wrapper.autopkg_wrapper import _needs_git_updates
from autopkg_wrapper.models.recipe import Recipe


def _clean_recipe(identifier: str = "Test.upload.jamf") -> Recipe:
    """A freshly-initialised recipe — defaults match a clean run."""
    return Recipe(identifier)


class TestNeedsGitUpdates:
    def test_empty_list_does_not_need_updates(self) -> None:
        # Degenerate case: no recipes at all.
        assert _needs_git_updates([]) is False

    def test_all_clean_recipes_do_not_need_updates(self) -> None:
        # Every recipe's defaults: updated=False, verified=None.
        # This is the "everything ran cleanly" state — the point of
        # the helper is that it returns False here so the skip-log
        # is downgraded to DEBUG.
        recipes = [_clean_recipe(f"Test{i}.upload.jamf") for i in range(3)]
        assert _needs_git_updates(recipes) is False

    def test_recipe_with_updated_true_needs_updates(self) -> None:
        r = _clean_recipe()
        r.updated = True
        assert _needs_git_updates([r]) is True

    def test_recipe_with_verified_false_needs_updates(self) -> None:
        # verified=False is the signal that trust verification failed
        # and process_recipe went down the update_trust_info arm —
        # there's a modified recipe file to commit.
        r = _clean_recipe()
        r.verified = False
        assert _needs_git_updates([r]) is True

    def test_verified_true_alone_does_not_need_updates(self) -> None:
        # Recipe ran successfully after trust verification passed;
        # nothing for the git-update pass to do.
        r = _clean_recipe()
        r.verified = True
        assert _needs_git_updates([r]) is False

    def test_verified_none_alone_does_not_need_updates(self) -> None:
        # process_recipe wasn't called or bailed before setting verified.
        # Treat as "no git work" — if the caller needed git work
        # they'd have set updated=True explicitly.
        r = _clean_recipe()
        assert r.verified is None  # precondition
        assert _needs_git_updates([r]) is False

    def test_one_dirty_recipe_flips_whole_batch(self) -> None:
        # Mixed batch: 2 clean + 1 with a failed trust check.
        # Should return True because the batch as a whole needs work.
        clean_a = _clean_recipe("A.upload.jamf")
        dirty = _clean_recipe("B.upload.jamf")
        dirty.verified = False
        clean_c = _clean_recipe("C.upload.jamf")
        assert _needs_git_updates([clean_a, dirty, clean_c]) is True

    def test_both_flags_set_needs_updates(self) -> None:
        # Defensive: updated=True AND verified=False are not exclusive
        # in principle. Either alone is enough; both together still
        # means work.
        r = _clean_recipe()
        r.updated = True
        r.verified = False
        assert _needs_git_updates([r]) is True

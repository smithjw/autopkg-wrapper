from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from autopkg_wrapper.utils import git_functions as gf


class DummyRecipe:
    def __init__(self, name, results):
        self.filename = f"{name}.recipe"
        self.results = results

    @property
    def name(self):
        return self.filename.split(".")[0]


class TestGitFunctions:
    def test_get_repo_info_parses_url(self):
        with patch.object(gf, "git_run") as git_run:
            git_run.return_value = SimpleNamespace(
                stdout="https://github.com/example-org/example-repo.git\n"
            )
            url, ref = gf.get_repo_info("--git-dir=/tmp/repo/.git")

        assert url == "https://github.com/example-org/example-repo"
        assert ref == "example-org/example-repo"

    def test_get_repo_info_parses_ssh_remote(self):
        with patch.object(gf, "git_run") as git_run:
            git_run.return_value = SimpleNamespace(
                stdout="git@github.com:Example-Org/Example-Repo.git\n"
            )
            url, ref = gf.get_repo_info("--git-dir=/tmp/repo/.git")

        assert url == "https://github.com/Example-Org/Example-Repo"
        assert ref == "Example-Org/Example-Repo"

    def test_create_issue_for_failed_recipes_none_when_empty(self):
        git_info = {
            "github_token": "t",
            "override_repo_remote_ref": "o/r",
            "override_repo_url": "https://github.com/o/r",
        }
        assert gf.create_issue_for_failed_recipes(git_info, []) is None

    def test_create_issue_for_failed_recipes_creates_issue(self):
        git_info = {
            "github_token": "t",
            "override_repo_remote_ref": "o/r",
            "override_repo_url": "https://github.com/o/r",
        }
        failed = [
            DummyRecipe(
                "BadRecipe",
                {
                    "failed": [
                        {"message": "trust error", "traceback": "tb"},
                    ]
                },
            )
        ]

        mock_issue = SimpleNamespace(number=123)
        mock_repo = MagicMock()
        mock_repo.create_issue.return_value = mock_issue
        mock_github = MagicMock()
        mock_github.get_repo.return_value = mock_repo

        with patch.object(gf, "Github", return_value=mock_github):
            url = gf.create_issue_for_failed_recipes(git_info, failed)

        assert url == "https://github.com/o/r/issues/123"
        args, kwargs = mock_repo.create_issue.call_args
        assert "AutoPkg Recipe Failures" in kwargs["title"]
        assert "BadRecipe" in kwargs["body"]
        assert kwargs["labels"] == ["autopkg-failure"]

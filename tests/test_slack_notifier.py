import json
from types import SimpleNamespace
from unittest.mock import patch

from autopkg_wrapper.notifier import slack


class DummyRecipe:
    def __init__(self, name):
        self.filename = f"{name}.recipe"
        self.verified = None
        self.error = False
        self.updated = False
        self.results = {"failed": [], "message": ""}

    @property
    def name(self):
        return self.filename.split(".")[0]


class TestSlackNotifier:
    def test_no_token_no_post(self):
        r = DummyRecipe("Foo")
        with patch.object(slack.requests, "post") as post:
            slack.send_notification(r, None)
            post.assert_not_called()

    def test_trust_failure_posts(self):
        r = DummyRecipe("Foo")
        r.verified = False
        r.results["message"] = "bad trust"

        with patch.object(slack.requests, "post") as post:
            post.return_value = SimpleNamespace(status_code=200, text="ok")
            slack.send_notification(r, "https://hooks.slack")

        args, kwargs = post.call_args
        assert args[0] == "https://hooks.slack"
        payload = json.loads(kwargs["data"])
        attachment = payload["attachments"][0]
        assert "failed trust verification" in attachment["title"]
        assert attachment["text"] == "bad trust"

    def test_error_unknown_posts(self):
        r = DummyRecipe("Foo")
        r.verified = True
        r.error = True
        r.results["failed"] = []

        with patch.object(slack.requests, "post") as post:
            post.return_value = SimpleNamespace(status_code=200, text="ok")
            slack.send_notification(r, "https://hooks.slack")

        payload = json.loads(post.call_args.kwargs["data"])
        assert "Unknown error" in payload["attachments"][0]["text"]

    def test_error_no_releases_skips(self):
        r = DummyRecipe("Foo")
        r.verified = True
        r.error = True
        r.results["failed"] = [
            {"message": "No releases found for repo", "traceback": "tb"}
        ]

        with patch.object(slack.requests, "post") as post:
            slack.send_notification(r, "https://hooks.slack")
            post.assert_not_called()

    def test_updated_posts(self):
        r = DummyRecipe("Foo")
        r.verified = True
        r.updated = True

        with patch.object(slack.requests, "post") as post:
            post.return_value = SimpleNamespace(status_code=200, text="ok")
            slack.send_notification(r, "https://hooks.slack")

        payload = json.loads(post.call_args.kwargs["data"])
        assert "has been uploaded" in payload["attachments"][0]["title"]

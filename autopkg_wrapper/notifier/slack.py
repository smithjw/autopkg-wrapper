import json
import logging

import requests


def send_notification(recipe, token):
    logging.debug("Skipping Slack notification as DEBUG is enabled!")

    if token is None:
        logging.error("Skipping Slack Notification as no SLACK_WEBHOOK_TOKEN defined!")
        return

    if recipe.verified is False:
        task_title = f"{recipe.name} failed trust verification"
        task_description = recipe.results["message"]
    elif recipe.error:
        task_title = f"Failed to import {recipe.name}"
        if not recipe.results["failed"]:
            task_description = "Unknown error"
        else:
            task_description = ("Error: {} \n" "Traceback: {} \n").format(
                recipe.results["failed"][0]["message"],
                recipe.results["failed"][0]["traceback"],
            )

            if "No releases found for repo" in task_description:
                return
    elif recipe.updated:
        task_title = f"{recipe.name} has been uploaded to Jamf"
        task_description = f"It's time to test {recipe.name}!"
    else:
        return

    response = requests.post(
        token,
        data=json.dumps(
            {
                "attachments": [
                    {
                        "username": "Autopkg",
                        "as_user": True,
                        "title": task_title,
                        "color": "warning"
                        if not recipe.verified
                        else "good"
                        if not recipe.error
                        else "danger",
                        "text": task_description,
                        "mrkdwn_in": ["text"],
                    }
                ]
            }
        ),
        headers={"Content-Type": "application/json"},
    )
    if response.status_code != 200:
        raise ValueError(
            "Request to slack returned an error %s, the response is:\n%s"
            % (response.status_code, response.text)
        )

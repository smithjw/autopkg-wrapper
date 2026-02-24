import json
import logging

import requests


def send_notification(recipe, token):
    logging.debug("Preparing Slack notification")

    if token is None:
        logging.error("Skipping Slack Notification as no SLACK_WEBHOOK_TOKEN defined!")
        return

    recipe_identifier = getattr(recipe, "identifier", None) or recipe.name

    if recipe.verified is False:
        task_title = f"{recipe_identifier} failed trust verification"
        # Get message from failed list or fall back to a generic message
        if recipe.results.get("failed") and recipe.results["failed"]:
            task_description = recipe.results["failed"][0].get(
                "message", "Trust verification failed"
            )
        else:
            task_description = "Trust verification failed"
    elif recipe.error:
        task_title = f"Failed to import {recipe_identifier}"
        if not recipe.results.get("failed"):
            task_description = "Unknown error"
        else:
            error_info = recipe.results["failed"][0]
            error_message = error_info.get("message", "Unknown error")
            error_traceback = error_info.get("traceback", "")

            if error_traceback:
                task_description = (
                    f"Error: {error_message}\nTraceback: {error_traceback}\n"
                )
            else:
                task_description = f"Error: {error_message}"

            if "No releases found for repo" in task_description:
                return
    elif recipe.updated:
        task_title = f"{recipe_identifier} has been uploaded to Jamf"
        task_description = f"It's time to test {recipe_identifier}!"
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
            "Request to slack returned an error "
            f"{response.status_code}, the response is:\n{response.text}"
        )

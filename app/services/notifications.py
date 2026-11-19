import logging

from fastapi import BackgroundTasks
from kombu.exceptions import OperationalError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def publish_assignment_email(task_id: int, assignee_id: int) -> None:
    # Runs in Starlette's thread pool after the response, never on the event loop.
    from app.jobs import send_assignment_email

    try:
        send_assignment_email.apply_async(
            args=[task_id, assignee_id],
            retry=False,
            expires=get_settings().assignment_email_expires_seconds,
        )
    except (OperationalError, OSError):
        # The task write is already committed. Do not turn it into an HTTP error.
        logger.error("Assignment email could not be queued for task_id=%s", task_id)


class AssignmentNotifications:
    def __init__(self, background: BackgroundTasks, *, enabled: bool) -> None:
        self.background = background
        self.enabled = enabled

    def assigned(self, task_id: int, assignee_id: int | None) -> None:
        if self.enabled and assignee_id is not None:
            self.background.add_task(publish_assignment_email, task_id, assignee_id)

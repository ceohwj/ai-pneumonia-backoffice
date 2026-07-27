from celery import Celery

from app.core.config import settings


celery_app = Celery(
    "background_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks"],
)

celery_app.conf.update(
    result_expires=settings.CELERY_RESULT_EXPIRES,
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=False,
    task_routes={
        "app.tasks.send_email": {
            "queue": "email_queue",
        },
    },
)

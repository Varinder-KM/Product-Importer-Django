import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.conf import settings  # noqa: E402

app = Celery("config")

app.config_from_object("django.conf:settings", namespace="CELERY")
app.conf.update(
    broker_url=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND,
    task_track_started=getattr(settings, "CELERY_TASK_TRACK_STARTED", True),
    result_extended=getattr(settings, "CELERY_RESULT_EXTENDED", True),
)
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")


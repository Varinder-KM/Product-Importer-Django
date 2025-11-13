import time
from datetime import timedelta
from typing import Any, Dict, Optional

import requests
from celery import shared_task
from django.utils import timezone

from .models import Webhook, WebhookDelivery

DEFAULT_TIMEOUT_SECONDS = 10
MAX_BACKOFF_SECONDS = 60


def _create_delivery(
    webhook: Webhook,
    event_type: str,
    payload: Dict[str, Any],
    *,
    is_test: bool = False,
    max_attempts: Optional[int] = None,
) -> WebhookDelivery:
    delivery = WebhookDelivery.objects.create(
        webhook=webhook,
        event_type=event_type,
        payload=payload,
        is_test=is_test,
        max_attempts=max_attempts or WebhookDelivery._meta.get_field("max_attempts").default,
    )
    return delivery


def _queue_delivery(delivery: WebhookDelivery) -> None:
    send_webhook.delay(delivery.id)


def queue_event(event_type: str, payload: Dict[str, Any]) -> int:
    webhooks = Webhook.objects.filter(enabled=True, event_type=event_type)
    count = 0
    for webhook in webhooks:
        delivery = _create_delivery(webhook, event_type, payload, is_test=False)
        _queue_delivery(delivery)
        count += 1
    return count


def queue_webhook(webhook: Webhook, event_type: str, payload: Dict[str, Any], *, is_test: bool = False) -> WebhookDelivery:
    delivery = _create_delivery(webhook, event_type, payload, is_test=is_test)
    _queue_delivery(delivery)
    return delivery


@shared_task(bind=True, name="webhooks.send_webhook", max_retries=5)
def send_webhook(self, delivery_id: int) -> None:
    try:
        delivery = WebhookDelivery.objects.select_related("webhook").get(pk=delivery_id)
    except WebhookDelivery.DoesNotExist:
        return

    webhook = delivery.webhook
    if not webhook.enabled:
        delivery.status = WebhookDelivery.Status.FAILED
        delivery.error_message = "Webhook disabled"
        delivery.save(update_fields=["status", "error_message", "updated_at"])
        return

    attempt = delivery.attempt + 1
    delivery.attempt = attempt
    delivery.status = WebhookDelivery.Status.IN_PROGRESS
    delivery.error_message = ""
    delivery.save(update_fields=["attempt", "status", "error_message", "updated_at"])

    start = time.perf_counter()
    error_message = ""
    response_code: Optional[int] = None

    try:
        response = requests.post(
            webhook.url,
            json=delivery.payload,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            headers={"Content-Type": "application/json"},
        )
        response_code = response.status_code
        if response.status_code >= 400:
            error_message = f"HTTP {response.status_code}: {response.text[:500]}"
            raise requests.HTTPError(error_message, response=response)
    except Exception as exc:
        error_message = str(exc) or error_message or "Webhook request failed"
        duration_ms = int((time.perf_counter() - start) * 1000)
        delivery.status = (
            WebhookDelivery.Status.RETRY
            if attempt < delivery.max_attempts
            else WebhookDelivery.Status.FAILED
        )
        delivery.response_code = response_code
        delivery.response_time_ms = duration_ms
        delivery.error_message = error_message
        delivery.next_retry_at = (
            timezone.now()
            + timedelta(seconds=min(MAX_BACKOFF_SECONDS, 2 ** attempt))
            if delivery.status == WebhookDelivery.Status.RETRY
            else None
        )
        delivery.save(
            update_fields=[
                "status",
                "response_code",
                "response_time_ms",
                "error_message",
                "next_retry_at",
                "updated_at",
            ]
        )

        webhook.last_status_code = response_code
        webhook.last_response_time_ms = duration_ms
        webhook.last_error = error_message
        webhook.save(update_fields=["last_status_code", "last_response_time_ms", "last_error", "updated_at"])

        if delivery.status == WebhookDelivery.Status.RETRY:
            countdown = min(MAX_BACKOFF_SECONDS, 2 ** attempt)
            raise self.retry(countdown=countdown)
        return

    duration_ms = int((time.perf_counter() - start) * 1000)
    delivery.status = WebhookDelivery.Status.SUCCESS
    delivery.response_code = response_code
    delivery.response_time_ms = duration_ms
    delivery.error_message = ""
    delivery.next_retry_at = None
    delivery.save(
        update_fields=[
            "status",
            "response_code",
            "response_time_ms",
            "error_message",
            "next_retry_at",
            "updated_at",
        ]
    )

    webhook.last_status_code = response_code
    webhook.last_response_time_ms = duration_ms
    webhook.last_error = ""
    webhook.save(update_fields=["last_status_code", "last_response_time_ms", "last_error", "updated_at"])


@shared_task(bind=True, name="webhooks.test_webhook")
def test_webhook(self, webhook_id: int) -> Optional[int]:
    try:
        webhook = Webhook.objects.get(pk=webhook_id)
    except Webhook.DoesNotExist:
        return None

    payload = {
        "event": Webhook.EVENT_WEBHOOK_TEST,
        "webhook_id": webhook.id,
        "timestamp": timezone.now().isoformat(),
        "message": "This is a test webhook payload.",
    }
    delivery = _create_delivery(webhook, Webhook.EVENT_WEBHOOK_TEST, payload, is_test=True, max_attempts=1)
    _queue_delivery(delivery)
    return delivery.id


from django.conf import settings
from django.db import models


class Webhook(models.Model):
    EVENT_PRODUCT_CREATED = "product.created"
    EVENT_PRODUCT_UPDATED = "product.updated"
    EVENT_PRODUCT_DELETED = "product.deleted"
    EVENT_IMPORT_PROGRESS = "product.import_progress"
    EVENT_IMPORT_COMPLETED = "product.import_completed"
    EVENT_WEBHOOK_TEST = "webhook.test"

    EVENT_CHOICES = [
        (EVENT_PRODUCT_CREATED, "Product Created"),
        (EVENT_PRODUCT_UPDATED, "Product Updated"),
        (EVENT_PRODUCT_DELETED, "Product Deleted"),
        (EVENT_IMPORT_PROGRESS, "Product Import Progress"),
        (EVENT_IMPORT_COMPLETED, "Product Import Completed"),
        (EVENT_WEBHOOK_TEST, "Webhook Test"),
    ]

    name = models.CharField(max_length=255)
    url = models.URLField()
    event_type = models.CharField(max_length=64, choices=EVENT_CHOICES)
    enabled = models.BooleanField(default=True)
    last_status_code = models.IntegerField(null=True, blank=True)
    last_response_time_ms = models.IntegerField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.event_type})"


class WebhookDelivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In Progress"
        SUCCESS = "success", "Success"
        RETRY = "retry", "Retrying"
        FAILED = "failed", "Failed"

    webhook = models.ForeignKey(
        Webhook, related_name="deliveries", on_delete=models.CASCADE
    )
    event_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=32, choices=Status.choices, default=Status.PENDING
    )
    attempt = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    response_code = models.IntegerField(null=True, blank=True)
    response_time_ms = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    is_test = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"WebhookDelivery #{self.pk} ({self.event_type})"


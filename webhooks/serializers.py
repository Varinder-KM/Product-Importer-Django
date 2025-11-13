from rest_framework import serializers

from .models import Webhook, WebhookDelivery


class WebhookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Webhook
        fields = [
            "id",
            "name",
            "url",
            "event_type",
            "enabled",
            "last_status_code",
            "last_response_time_ms",
            "last_error",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "last_status_code",
            "last_response_time_ms",
            "last_error",
            "created_at",
            "updated_at",
        ]


class WebhookDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookDelivery
        fields = [
            "id",
            "webhook",
            "event_type",
            "status",
            "attempt",
            "max_attempts",
            "response_code",
            "response_time_ms",
            "error_message",
            "next_retry_at",
            "is_test",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


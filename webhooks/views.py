from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Webhook
from .serializers import WebhookSerializer
from .tasks import test_webhook


class WebhookViewSet(viewsets.ModelViewSet):
    queryset = Webhook.objects.all().order_by("-created_at")
    serializer_class = WebhookSerializer
    permission_classes = [permissions.AllowAny]

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        webhook = self.get_object()
        task = test_webhook.delay(webhook.id)
        return Response(
            {
                "status": "queued",
                "task_id": task.id,
                "webhook_id": webhook.id,
            },
            status=status.HTTP_202_ACCEPTED,
        )


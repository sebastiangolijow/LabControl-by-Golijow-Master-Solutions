"""Views for notifications app."""
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(viewsets.ModelViewSet):
    """ViewSet for managing notifications."""

    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Users can only see their own notifications."""
        return Notification.objects.filter(user=self.request.user)

    @action(detail=True, methods=["post"])
    def mark_as_read(self, request, pk=None):
        """Mark a notification as read."""
        notification = self.get_object()
        if not notification.is_read:
            notification.read_at = timezone.now()
            notification.status = "read"
            notification.save(update_fields=["read_at", "status"])

        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def mark_all_as_read(self, request):
        """Mark all notifications as read for the current user."""
        updated = Notification.objects.filter(
            user=request.user, read_at__isnull=True
        ).update(read_at=timezone.now(), status="read")

        return Response(
            {"message": f"{updated} notifications marked as read"},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        """Get count of unread notifications."""
        count = Notification.objects.filter(
            user=request.user, read_at__isnull=True
        ).count()

        return Response({"unread_count": count})

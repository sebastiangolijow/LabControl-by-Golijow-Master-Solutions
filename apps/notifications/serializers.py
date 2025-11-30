"""Serializers for notifications app."""

from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for Notification model."""

    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "uuid",
            "title",
            "message",
            "notification_type",
            "channel",
            "status",
            "is_read",
            "related_study_id",
            "related_appointment_id",
            "related_invoice_id",
            "metadata",
            "created_at",
            "read_at",
        ]
        read_only_fields = ["uuid", "created_at"]

"""Serializers for appointments app."""
from rest_framework import serializers

from .models import Appointment


class AppointmentSerializer(serializers.ModelSerializer):
    """Serializer for Appointment model."""

    patient_email = serializers.EmailField(source="patient.email", read_only=True)
    is_upcoming = serializers.BooleanField(read_only=True)

    class Meta:
        model = Appointment
        fields = [
            "id",
            "uuid",
            "appointment_number",
            "patient",
            "patient_email",
            "study",
            "scheduled_date",
            "scheduled_time",
            "duration_minutes",
            "status",
            "reason",
            "notes",
            "is_upcoming",
            "reminder_sent",
            "created_at",
        ]
        read_only_fields = ["uuid", "appointment_number", "created_at"]

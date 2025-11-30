"""Serializers for appointments app."""

from datetime import date

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


class AppointmentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating appointments."""

    class Meta:
        model = Appointment
        fields = [
            "patient",
            "study",
            "scheduled_date",
            "scheduled_time",
            "duration_minutes",
            "reason",
            "notes",
        ]

    def __init__(self, *args, **kwargs):
        """Initialize serializer and set patient field based on request user."""
        super().__init__(*args, **kwargs)
        request = self.context.get("request")

        # Make patient field optional for patient users
        if request and hasattr(request, "user") and request.user.is_patient:
            self.fields["patient"].required = False
            self.fields["patient"].allow_null = True

    def validate_scheduled_date(self, value):
        """Validate that appointment is not in the past."""
        if value < date.today():
            raise serializers.ValidationError(
                "Cannot schedule an appointment in the past."
            )
        return value

    def validate(self, attrs):
        """Additional validation."""
        # Can add more validation here, such as:
        # - Check for conflicting appointments
        # - Validate business hours
        # - Check lab capacity
        return attrs

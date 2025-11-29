"""Tests for appointments app."""
import pytest
from datetime import date, time
from apps.appointments.models import Appointment
from rest_framework import status


@pytest.fixture
def appointment(db, user):
    """Fixture for creating an appointment."""
    return Appointment.objects.create(
        patient=user,
        appointment_number="APT-2024-001",
        scheduled_date=date(2024, 12, 15),
        scheduled_time=time(10, 0),
        duration_minutes=30,
        status="scheduled",
        reason="Blood sample collection",
        lab_client_id=1,
    )


@pytest.mark.django_db
class TestAppointmentModel:
    """Test cases for Appointment model."""

    def test_create_appointment(self, appointment):
        """Test creating an appointment."""
        assert appointment.appointment_number == "APT-2024-001"
        assert appointment.status == "scheduled"
        assert appointment.duration_minutes == 30

    def test_appointment_str_representation(self, appointment, user):
        """Test appointment string representation."""
        expected = f"APT-2024-001 - {user.email} on 2024-12-15"
        assert str(appointment) == expected

    def test_appointment_is_completed(self, appointment):
        """Test appointment completion status."""
        assert appointment.is_completed is False
        appointment.status = "completed"
        assert appointment.is_completed is True


@pytest.mark.django_db
class TestAppointmentAPI:
    """Test cases for Appointment API endpoints."""

    def test_list_patient_appointments(self, authenticated_client, appointment):
        """Test patient can see their own appointments."""
        response = authenticated_client.get("/api/v1/appointments/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["appointment_number"] == appointment.appointment_number

"""Tests for appointments app following TDD principles."""

from datetime import date, time, timedelta

from django.utils import timezone
from rest_framework import status

from apps.appointments.models import Appointment
from tests.base import BaseTestCase


class TestAppointmentModel(BaseTestCase):
    """Test cases for Appointment model."""

    def test_create_appointment(self):
        """Test creating an appointment."""
        patient = self.create_patient()
        appointment = self.create_appointment(patient=patient)

        assert appointment.patient == patient
        assert appointment.status == "scheduled"
        assert appointment.duration_minutes == 30
        assert appointment.appointment_number is not None

    def test_appointment_has_uuid(self):
        """Test that appointment has UUID field."""
        appointment = self.create_appointment()
        self.assertUUID(appointment.uuid)

    def test_appointment_has_timestamps(self):
        """Test that appointment has timestamp fields."""
        appointment = self.create_appointment()
        self.assertIsNotNone(appointment.created_at)
        self.assertIsNotNone(appointment.updated_at)
        self.assertTimestampRecent(appointment.created_at)

    def test_appointment_has_audit_trail(self):
        """Test that appointment has history tracking."""
        appointment = self.create_appointment()
        assert hasattr(appointment, "history")
        assert appointment.history.count() == 1  # Created

        # Update appointment
        appointment.status = "confirmed"
        appointment.save()
        assert appointment.history.count() == 2  # Created + Updated

    def test_appointment_created_by(self):
        """Test created_by field."""
        admin = self.create_admin()
        appointment = self.create_appointment(created_by=admin)

        assert appointment.created_by == admin

    def test_appointment_str_representation(self):
        """Test appointment string representation."""
        patient = self.create_patient(email="patient@test.com")
        appointment = self.create_appointment(
            patient=patient,
            appointment_number="APT-001",
            scheduled_date=date(2024, 12, 15),
        )
        expected = "APT-001 - patient@test.com on 2024-12-15"
        assert str(appointment) == expected

    def test_appointment_is_completed_property(self):
        """Test is_completed property."""
        appointment = self.create_appointment(status="scheduled")
        assert appointment.is_completed is False

        appointment.status = "completed"
        appointment.save()
        assert appointment.is_completed is True

    def test_appointment_is_upcoming_property(self):
        """Test is_upcoming property."""
        # Future scheduled appointment
        future_date = timezone.now().date() + timedelta(days=7)
        appointment = self.create_appointment(
            scheduled_date=future_date,
            status="scheduled",
        )
        assert appointment.is_upcoming is True

        # Past scheduled appointment
        past_date = timezone.now().date() - timedelta(days=7)
        appointment = self.create_appointment(
            scheduled_date=past_date,
            status="scheduled",
        )
        assert appointment.is_upcoming is False

        # Future but cancelled
        appointment = self.create_appointment(
            scheduled_date=future_date,
            status="cancelled",
        )
        assert appointment.is_upcoming is False

    def test_appointment_with_study(self):
        """Test appointment linked to a study."""
        patient = self.create_patient()
        study = self.create_study(patient=patient)
        appointment = self.create_appointment(
            patient=patient,
            study=study,
        )

        assert appointment.study == study
        assert appointment in study.appointments.all()


class TestAppointmentManager(BaseTestCase):
    """Test cases for Appointment custom manager."""

    def test_scheduled_appointments(self):
        """Test AppointmentManager.scheduled() method."""
        scheduled = self.create_appointment(status="scheduled")
        confirmed = self.create_appointment(status="confirmed")

        scheduled_appointments = Appointment.objects.scheduled()
        assert scheduled in scheduled_appointments
        assert confirmed not in scheduled_appointments

    def test_confirmed_appointments(self):
        """Test AppointmentManager.confirmed() method."""
        scheduled = self.create_appointment(status="scheduled")
        confirmed = self.create_appointment(status="confirmed")

        confirmed_appointments = Appointment.objects.confirmed()
        assert confirmed in confirmed_appointments
        assert scheduled not in confirmed_appointments

    def test_completed_appointments(self):
        """Test AppointmentManager.completed() method."""
        scheduled = self.create_appointment(status="scheduled")
        completed = self.create_appointment(status="completed")

        completed_appointments = Appointment.objects.completed()
        assert completed in completed_appointments
        assert scheduled not in completed_appointments

    def test_cancelled_appointments(self):
        """Test AppointmentManager.cancelled() method."""
        scheduled = self.create_appointment(status="scheduled")
        cancelled = self.create_appointment(status="cancelled")

        cancelled_appointments = Appointment.objects.cancelled()
        assert cancelled in cancelled_appointments
        assert scheduled not in cancelled_appointments

    def test_upcoming_appointments(self):
        """Test AppointmentManager.upcoming() method."""
        future_date = timezone.now().date() + timedelta(days=7)
        past_date = timezone.now().date() - timedelta(days=7)

        upcoming = self.create_appointment(
            scheduled_date=future_date,
            status="scheduled",
        )
        past = self.create_appointment(
            scheduled_date=past_date,
            status="scheduled",
        )

        upcoming_appointments = Appointment.objects.upcoming()
        assert upcoming in upcoming_appointments
        assert past not in upcoming_appointments

    def test_past_appointments(self):
        """Test AppointmentManager.past() method."""
        future_date = timezone.now().date() + timedelta(days=7)
        past_date = timezone.now().date() - timedelta(days=7)

        upcoming = self.create_appointment(scheduled_date=future_date)
        past = self.create_appointment(scheduled_date=past_date)

        past_appointments = Appointment.objects.past()
        assert past in past_appointments
        assert upcoming not in past_appointments

    def test_today_appointments(self):
        """Test AppointmentManager.today() method."""
        today = timezone.now().date()
        tomorrow = today + timedelta(days=1)

        today_apt = self.create_appointment(scheduled_date=today)
        tomorrow_apt = self.create_appointment(scheduled_date=tomorrow)

        today_appointments = Appointment.objects.today()
        assert today_apt in today_appointments
        assert tomorrow_apt not in today_appointments

    def test_for_patient(self):
        """Test AppointmentManager.for_patient() method."""
        patient1 = self.create_patient()
        patient2 = self.create_patient(email="patient2@test.com")

        apt1 = self.create_appointment(patient=patient1)
        apt2 = self.create_appointment(patient=patient2)

        patient1_apts = Appointment.objects.for_patient(patient1)
        assert apt1 in patient1_apts
        assert apt2 not in patient1_apts

    def test_for_study(self):
        """Test AppointmentManager.for_study() method."""
        patient = self.create_patient()
        study1 = self.create_study(patient=patient)
        study2 = self.create_study(patient=patient)

        apt1 = self.create_appointment(patient=patient, study=study1)
        apt2 = self.create_appointment(patient=patient, study=study2)

        study1_apts = Appointment.objects.for_study(study1)
        assert apt1 in study1_apts
        assert apt2 not in study1_apts

    def test_for_lab(self):
        """Test AppointmentManager.for_lab() method."""
        lab1_appointment = self.create_appointment(lab_client_id=1)
        lab2_appointment = self.create_appointment(lab_client_id=2)

        lab1_appointments = Appointment.objects.for_lab(1)
        assert lab1_appointment in lab1_appointments
        assert lab2_appointment not in lab1_appointments

    def test_checked_in(self):
        """Test AppointmentManager.checked_in() method."""
        checked_in = self.create_appointment(checked_in_at=timezone.now())
        not_checked_in = self.create_appointment(checked_in_at=None)

        checked_in_appointments = Appointment.objects.checked_in()
        assert checked_in in checked_in_appointments
        assert not_checked_in not in checked_in_appointments

    def test_not_checked_in(self):
        """Test AppointmentManager.not_checked_in() method."""
        checked_in = self.create_appointment(checked_in_at=timezone.now())
        not_checked_in = self.create_appointment(checked_in_at=None)

        not_checked_in_appointments = Appointment.objects.not_checked_in()
        assert not_checked_in in not_checked_in_appointments
        assert checked_in not in not_checked_in_appointments

    def test_chainable_queries(self):
        """Test that manager methods are chainable."""
        future_date = timezone.now().date() + timedelta(days=7)

        lab1_upcoming = self.create_appointment(
            lab_client_id=1,
            scheduled_date=future_date,
            status="scheduled",
        )
        lab2_upcoming = self.create_appointment(
            lab_client_id=2,
            scheduled_date=future_date,
            status="scheduled",
        )
        lab1_past = self.create_appointment(
            lab_client_id=1,
            scheduled_date=timezone.now().date() - timedelta(days=7),
            status="scheduled",
        )

        # Chain: upcoming scheduled appointments in lab 1
        result = Appointment.objects.for_lab(1).upcoming().scheduled()

        assert lab1_upcoming in result
        assert lab2_upcoming not in result
        assert lab1_past not in result


class TestAppointmentAPI(BaseTestCase):
    """Test cases for Appointment API endpoints."""

    def test_list_patient_appointments(self):
        """Test patient can see their own appointments."""
        client, patient = self.authenticate_as_patient()
        appointment = self.create_appointment(patient=patient)

        response = client.get("/api/v1/appointments/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert (
            response.data["results"][0]["appointment_number"]
            == appointment.appointment_number
        )

    def test_patient_cannot_see_other_appointments(self):
        """Test patient cannot see other patients' appointments."""
        client, patient1 = self.authenticate_as_patient()
        patient2 = self.create_patient(email="other@test.com")

        own_appointment = self.create_appointment(patient=patient1)
        _other_appointment = self.create_appointment(patient=patient2)  # noqa: F841

        response = client.get("/api/v1/appointments/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["id"] == own_appointment.id

    def test_lab_manager_can_see_lab_appointments(self):
        """Test lab manager can see all appointments for their lab."""
        client, manager = self.authenticate_as_lab_manager(lab_client_id=1)

        # Create appointments for different labs
        lab1_apt = self.create_appointment(lab_client_id=1)
        lab2_apt = self.create_appointment(lab_client_id=2)

        response = client.get("/api/v1/appointments/")
        assert response.status_code == status.HTTP_200_OK

        appointment_ids = [apt["id"] for apt in response.data["results"]]
        assert lab1_apt.id in appointment_ids
        assert lab2_apt.id not in appointment_ids

    def test_appointment_uuid_in_api_response(self):
        """Test that UUID is included in API responses."""
        client, patient = self.authenticate_as_patient()
        appointment = self.create_appointment(patient=patient)

        response = client.get("/api/v1/appointments/")
        assert response.status_code == status.HTTP_200_OK
        assert "uuid" in response.data["results"][0]
        self.assertUUID(appointment.uuid)

"""Tests for analytics app following TDD principles."""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from tests.base import BaseTestCase

from apps.analytics.services import StatisticsService


class TestAnalyticsPermissions(BaseTestCase):
    """Test permission controls for analytics endpoints."""

    def test_unauthenticated_cannot_access_dashboard(self):
        """Test that unauthenticated users cannot access dashboard."""
        response = self.client.get("/api/v1/analytics/dashboard/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_patient_cannot_access_analytics(self):
        """Test that patients cannot access analytics endpoints."""
        client, _user = self.authenticate_as_patient()
        response = client.get("/api/v1/analytics/dashboard/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_doctor_cannot_access_analytics(self):
        """Test that doctors cannot access analytics endpoints."""
        doctor = self.create_doctor()
        client = self.authenticate(doctor)
        response = client.get("/api/v1/analytics/dashboard/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_lab_staff_cannot_access_analytics(self):
        """Test that lab staff cannot access analytics endpoints."""
        staff = self.create_lab_staff()
        client = self.authenticate(staff)
        response = client.get("/api/v1/analytics/dashboard/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_lab_manager_can_access_analytics(self):
        """Test that lab managers can access analytics endpoints."""
        client, _user = self.authenticate_as_lab_manager()
        response = client.get("/api/v1/analytics/dashboard/")
        assert response.status_code == status.HTTP_200_OK

    def test_admin_can_access_analytics(self):
        """Test that admins can access analytics endpoints."""
        client, _user = self.authenticate_as_admin()
        response = client.get("/api/v1/analytics/dashboard/")
        assert response.status_code == status.HTTP_200_OK


class TestDashboardSummaryAPI(BaseTestCase):
    """Test dashboard summary endpoint."""

    def test_dashboard_summary_structure(self):
        """Test that dashboard summary returns correct structure."""
        client, _user = self.authenticate_as_lab_manager()

        response = client.get("/api/v1/analytics/dashboard/")
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert "studies" in data
        assert "revenue" in data
        assert "appointments" in data
        assert "users" in data
        assert "period" in data

    def test_lab_manager_sees_own_lab_only(self):
        """Test that lab managers only see their own lab's data."""
        # Create data for lab 1
        client, manager1 = self.authenticate_as_lab_manager(lab_client_id=1)
        patient1 = self.create_patient(lab_client_id=1)
        self.create_study(patient=patient1, lab_client_id=1)

        # Create data for lab 2
        patient2 = self.create_patient(lab_client_id=2, email="patient2@test.com")
        self.create_study(patient=patient2, lab_client_id=2)

        response = client.get("/api/v1/analytics/dashboard/")
        assert response.status_code == status.HTTP_200_OK

        # Should only see 1 study (lab 1)
        total_studies = response.data["studies"]["overview"]["total"]
        assert total_studies == 1

    def test_admin_can_filter_by_lab(self):
        """Test that admins can filter dashboard by lab_client_id."""
        client, _admin = self.authenticate_as_admin()

        # Create data for lab 1
        patient1 = self.create_patient(lab_client_id=1)
        self.create_study(patient=patient1, lab_client_id=1)

        # Create data for lab 2
        patient2 = self.create_patient(lab_client_id=2, email="patient2@test.com")
        self.create_study(patient=patient2, lab_client_id=2)
        self.create_study(patient=patient2, lab_client_id=2)

        # Filter by lab 2
        response = client.get("/api/v1/analytics/dashboard/?lab_client_id=2")
        assert response.status_code == status.HTTP_200_OK

        # Should only see 2 studies (lab 2)
        total_studies = response.data["studies"]["overview"]["total"]
        assert total_studies == 2


class TestStudyStatisticsAPI(BaseTestCase):
    """Test study statistics endpoints."""

    def test_study_statistics_counts_by_status(self):
        """Test that study statistics shows correct counts by status."""
        client, manager = self.authenticate_as_lab_manager(lab_client_id=1)
        patient = self.create_patient(lab_client_id=1)

        # Create studies with different statuses
        self.create_study(patient=patient, status="pending")
        self.create_study(patient=patient, status="in_progress")
        self.create_study(patient=patient, status="completed")
        self.create_study(patient=patient, status="completed")

        response = client.get("/api/v1/analytics/studies/")
        assert response.status_code == status.HTTP_200_OK

        overview = response.data["overview"]
        assert overview["total"] == 4
        assert overview["pending"] == 1
        assert overview["in_progress"] == 1
        assert overview["completed"] == 2

    def test_study_statistics_by_type(self):
        """Test that statistics show breakdown by study type."""
        client, _manager = self.authenticate_as_lab_manager(lab_client_id=1)
        patient = self.create_patient(lab_client_id=1)

        blood_test = self.create_study_type(name="Blood Test", code="BT001")
        xray = self.create_study_type(name="X-Ray", code="XR001")

        self.create_study(patient=patient, study_type=blood_test)
        self.create_study(patient=patient, study_type=blood_test)
        self.create_study(patient=patient, study_type=xray)

        response = client.get("/api/v1/analytics/studies/")
        assert response.status_code == status.HTTP_200_OK

        by_type = response.data["by_type"]
        assert len(by_type) == 2

        # Find blood test entry
        blood_entry = next(
            item for item in by_type if item["study_type__name"] == "Blood Test"
        )
        assert blood_entry["count"] == 2


class TestStudyTrendsAPI(BaseTestCase):
    """Test study trends endpoint."""

    def test_study_trends_by_month(self):
        """Test getting study trends grouped by month."""
        client, _manager = self.authenticate_as_lab_manager(lab_client_id=1)
        patient = self.create_patient(lab_client_id=1)

        # Create studies across different months
        now = timezone.now()
        for months_ago in [0, 1, 2]:
            study = self.create_study(patient=patient)
            study.created_at = now - timedelta(days=30 * months_ago)
            study.save()

        start_date = (now - timedelta(days=90)).isoformat()
        response = client.get(
            f"/api/v1/analytics/studies/trends/?period=month&start_date={start_date}"
        )
        assert response.status_code == status.HTTP_200_OK

        trends = response.data
        assert len(trends) >= 1  # At least one period should have data


class TestRevenueStatisticsAPI(BaseTestCase):
    """Test revenue statistics endpoints."""

    def test_revenue_statistics_shows_invoices_and_payments(self):
        """Test that revenue statistics shows correct financial data."""
        client, _manager = self.authenticate_as_lab_manager(lab_client_id=1)
        patient = self.create_patient(lab_client_id=1)
        study = self.create_study(patient=patient)

        # Create invoices
        invoice1 = self.create_invoice(
            patient=patient,
            study=study,
            total_amount=Decimal("500.00"),
            paid_amount=Decimal("500.00"),
            status="paid",
        )
        invoice2 = self.create_invoice(
            patient=patient,
            study=study,
            total_amount=Decimal("300.00"),
            paid_amount=Decimal("0.00"),
            status="pending",
        )

        # Create payment
        self.create_payment(
            invoice=invoice1, amount=Decimal("500.00"), status="completed"
        )

        response = client.get("/api/v1/analytics/revenue/")
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert data["invoices"]["total_invoices"] == 2
        assert Decimal(data["invoices"]["total_amount"]) == Decimal("800.00")
        assert Decimal(data["invoices"]["total_paid"]) == Decimal("500.00")
        assert Decimal(data["outstanding_balance"]) == Decimal("300.00")

    def test_revenue_statistics_counts_by_payment_method(self):
        """Test that revenue statistics shows breakdown by payment method."""
        client, _manager = self.authenticate_as_lab_manager(lab_client_id=1)
        patient = self.create_patient(lab_client_id=1)
        study = self.create_study(patient=patient)

        invoice = self.create_invoice(patient=patient, study=study)

        # Create payments with different methods
        self.create_payment(invoice=invoice, payment_method="cash")
        self.create_payment(invoice=invoice, payment_method="credit_card")

        response = client.get("/api/v1/analytics/revenue/")
        assert response.status_code == status.HTTP_200_OK

        payments = response.data["payments"]
        assert payments["cash_payments"] == 1
        assert payments["card_payments"] == 1


class TestAppointmentStatisticsAPI(BaseTestCase):
    """Test appointment statistics endpoint."""

    def test_appointment_statistics_counts_by_status(self):
        """Test that appointment statistics shows counts by status."""
        client, _manager = self.authenticate_as_lab_manager(lab_client_id=1)
        patient = self.create_patient(lab_client_id=1)

        # Create appointments with different statuses
        self.create_appointment(patient=patient, status="scheduled")
        self.create_appointment(patient=patient, status="confirmed")
        self.create_appointment(patient=patient, status="completed")
        self.create_appointment(patient=patient, status="no_show")

        response = client.get("/api/v1/analytics/appointments/")
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert data["total"] == 4
        assert data["scheduled"] == 1
        assert data["confirmed"] == 1
        assert data["completed"] == 1
        assert data["no_show"] == 1

    def test_appointment_statistics_calculates_show_rate(self):
        """Test that show rate percentage is calculated correctly."""
        client, _manager = self.authenticate_as_lab_manager(lab_client_id=1)
        patient = self.create_patient(lab_client_id=1)

        # Create 3 completed and 1 no_show = 75% show rate
        for _ in range(3):
            self.create_appointment(patient=patient, status="completed")
        self.create_appointment(patient=patient, status="no_show")

        response = client.get("/api/v1/analytics/appointments/")
        assert response.status_code == status.HTTP_200_OK

        show_rate = response.data["show_rate_percentage"]
        assert show_rate == 75.0


class TestUserStatisticsAPI(BaseTestCase):
    """Test user statistics endpoint."""

    def test_user_statistics_counts_by_role(self):
        """Test that user statistics shows counts by role."""
        client, _manager = self.authenticate_as_lab_manager(lab_client_id=1)

        # Create users with different roles (all in lab 1)
        self.create_patient(lab_client_id=1)
        self.create_patient(lab_client_id=1, email="patient2@test.com")
        self.create_doctor(lab_client_id=1, email="doctor@test.com")
        self.create_lab_staff(lab_client_id=1, email="staff@test.com")

        response = client.get("/api/v1/analytics/users/")
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        # +1 for the lab_manager we authenticated with
        assert data["total_users"] >= 5
        assert data["patients"] >= 2
        assert data["doctors"] >= 1
        assert data["lab_staff"] >= 1


class TestPopularStudyTypesAPI(BaseTestCase):
    """Test popular study types endpoint."""

    def test_popular_study_types_shows_order_counts(self):
        """Test that popular study types are ranked by order count."""
        client, _manager = self.authenticate_as_lab_manager(lab_client_id=1)
        patient = self.create_patient(lab_client_id=1)

        # Create study types
        blood_test = self.create_study_type(name="Blood Test", code="BT001")
        xray = self.create_study_type(name="X-Ray", code="XR001")

        # Create more blood tests than x-rays
        for _ in range(3):
            self.create_study(patient=patient, study_type=blood_test)
        self.create_study(patient=patient, study_type=xray)

        response = client.get("/api/v1/analytics/popular-study-types/")
        assert response.status_code == status.HTTP_200_OK

        types = response.data
        assert len(types) >= 2

        # Blood test should be first (most popular)
        assert types[0]["study_type__name"] == "Blood Test"
        assert types[0]["order_count"] == 3


class TestTopRevenueStudyTypesAPI(BaseTestCase):
    """Test top revenue study types endpoint."""

    def test_top_revenue_study_types_ranked_by_revenue(self):
        """Test that study types are ranked by revenue generated."""
        client, _manager = self.authenticate_as_lab_manager(lab_client_id=1)
        patient = self.create_patient(lab_client_id=1)

        # Create study types
        expensive = self.create_study_type(
            name="MRI", code="MRI001", base_price=Decimal("1000.00")
        )
        cheap = self.create_study_type(
            name="Blood Test", code="BT001", base_price=Decimal("50.00")
        )

        # Create studies and invoices
        mri_study = self.create_study(patient=patient, study_type=expensive)
        blood_study = self.create_study(patient=patient, study_type=cheap)

        mri_invoice = self.create_invoice(
            patient=patient,
            study=mri_study,
            total_amount=Decimal("1000.00"),
            paid_amount=Decimal("1000.00"),
            status="paid",
        )
        blood_invoice = self.create_invoice(
            patient=patient,
            study=blood_study,
            total_amount=Decimal("50.00"),
            paid_amount=Decimal("50.00"),
            status="paid",
        )

        response = client.get("/api/v1/analytics/top-revenue-study-types/")
        assert response.status_code == status.HTTP_200_OK

        types = response.data
        assert len(types) >= 2

        # MRI should be first (highest revenue)
        assert types[0]["study__study_type__name"] == "MRI"
        assert Decimal(types[0]["total_revenue"]) == Decimal("1000.00")


class TestStatisticsServiceLayer(BaseTestCase):
    """Test statistics service layer directly."""

    def test_get_study_statistics_service(self):
        """Test study statistics service method."""
        patient = self.create_patient(lab_client_id=1)
        self.create_study(patient=patient, status="pending")
        self.create_study(patient=patient, status="completed")

        stats = StatisticsService.get_study_statistics(lab_client_id=1)

        assert stats["overview"]["total"] == 2
        assert stats["overview"]["pending"] == 1
        assert stats["overview"]["completed"] == 1
        assert "by_type" in stats

    def test_multi_tenant_isolation_in_service(self):
        """Test that service layer properly isolates data by lab."""
        # Lab 1 data
        patient1 = self.create_patient(lab_client_id=1)
        self.create_study(patient=patient1)

        # Lab 2 data
        patient2 = self.create_patient(lab_client_id=2, email="patient2@test.com")
        self.create_study(patient=patient2)
        self.create_study(patient=patient2)

        # Get stats for lab 1
        stats_lab1 = StatisticsService.get_study_statistics(lab_client_id=1)
        assert stats_lab1["overview"]["total"] == 1

        # Get stats for lab 2
        stats_lab2 = StatisticsService.get_study_statistics(lab_client_id=2)
        assert stats_lab2["overview"]["total"] == 2

    def test_get_revenue_statistics_service(self):
        """Test revenue statistics service method."""
        patient = self.create_patient(lab_client_id=1)
        study = self.create_study(patient=patient)

        invoice = self.create_invoice(
            patient=patient,
            study=study,
            total_amount=Decimal("500.00"),
            paid_amount=Decimal("200.00"),
            status="partially_paid",
        )

        stats = StatisticsService.get_revenue_statistics(lab_client_id=1)

        assert stats["invoices"]["total_invoices"] == 1
        assert stats["outstanding_balance"] == Decimal("300.00")

    def test_get_dashboard_summary_service(self):
        """Test dashboard summary service method."""
        patient = self.create_patient(lab_client_id=1)
        self.create_study(patient=patient)

        summary = StatisticsService.get_dashboard_summary(lab_client_id=1)

        assert "studies" in summary
        assert "revenue" in summary
        assert "appointments" in summary
        assert "users" in summary
        assert "period" in summary

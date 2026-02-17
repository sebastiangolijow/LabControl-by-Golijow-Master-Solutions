"""
Statistics service layer for analytics app.

This module handles all statistical calculations and aggregations.
Business logic is kept separate from views for better testability.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, F, FloatField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate, TruncMonth, TruncWeek
from django.utils import timezone

from apps.appointments.models import Appointment
from apps.notifications.models import Notification
from apps.payments.models import Invoice, Payment
from apps.studies.models import Practice, Study
from apps.users.models import User


class StatisticsService:
    """
    Service class for calculating various statistics.

    All methods support multi-tenant filtering via lab_client_id.
    """

    @staticmethod
    def get_study_statistics(lab_client_id=None, start_date=None, end_date=None):
        """
        Get comprehensive study statistics.

        Args:
            lab_client_id: Filter by lab client (multi-tenant)
            start_date: Filter studies created after this date
            end_date: Filter studies created before this date

        Returns:
            dict: Study statistics including counts by status and type
        """
        queryset = Study.objects.all()

        # Multi-tenant filtering
        if lab_client_id:
            queryset = queryset.for_lab(lab_client_id)

        # Date range filtering
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)

        # Count by status
        status_counts = queryset.aggregate(
            total=Count("pk"),
            pending=Count("pk", filter=Q(status="pending")),
            sample_collected=Count("pk", filter=Q(status="sample_collected")),
            in_progress=Count("pk", filter=Q(status="in_progress")),
            completed=Count("pk", filter=Q(status="completed")),
            cancelled=Count("pk", filter=Q(status="cancelled")),
        )

        # Count by practice
        by_practice = list(
            queryset.values("practice__name")
            .annotate(count=Count("pk"))
            .order_by("-count")
        )

        # Average processing time for completed studies
        avg_processing = queryset.filter(status="completed").aggregate(
            avg_hours=Avg(
                F("completed_at") - F("created_at"),
                output_field=FloatField(),
            )
        )

        return {
            "overview": status_counts,
            "by_practice": by_practice,
            "avg_processing_hours": (
                avg_processing["avg_hours"].total_seconds() / 3600
                if avg_processing["avg_hours"]
                else None
            ),
        }

    @staticmethod
    def get_study_trends(
        lab_client_id=None, period="month", start_date=None, end_date=None
    ):
        """
        Get study trends over time.

        Args:
            lab_client_id: Filter by lab client
            period: Grouping period ('day', 'week', 'month')
            start_date: Start date for trend data
            end_date: End date for trend data

        Returns:
            list: Time-series data of study counts
        """
        queryset = Study.objects.all()

        # Multi-tenant filtering
        if lab_client_id:
            queryset = queryset.for_lab(lab_client_id)

        # Default to last 6 months if no dates provided
        if not start_date:
            start_date = timezone.now() - timedelta(days=180)
        if not end_date:
            end_date = timezone.now()

        queryset = queryset.filter(created_at__gte=start_date, created_at__lte=end_date)

        # Group by period
        if period == "day":
            trunc_func = TruncDate
        elif period == "week":
            trunc_func = TruncWeek
        else:  # month
            trunc_func = TruncMonth

        trends = list(
            queryset.annotate(period=trunc_func("created_at"))
            .values("period")
            .annotate(
                total=Count("pk"),
                pending=Count("pk", filter=Q(status="pending")),
                in_progress=Count("pk", filter=Q(status="in_progress")),
                completed=Count("pk", filter=Q(status="completed")),
            )
            .order_by("period")
        )

        return trends

    @staticmethod
    def get_revenue_statistics(lab_client_id=None, start_date=None, end_date=None):
        """
        Get revenue and payment statistics.

        Args:
            lab_client_id: Filter by lab client
            start_date: Filter invoices created after this date
            end_date: Filter invoices created before this date

        Returns:
            dict: Revenue statistics
        """
        invoice_queryset = Invoice.objects.all()
        payment_queryset = Payment.objects.all()

        # Multi-tenant filtering
        if lab_client_id:
            invoice_queryset = invoice_queryset.for_lab(lab_client_id)
            # Payment filtering via invoice relationship
            payment_queryset = payment_queryset.filter(
                invoice__lab_client_id=lab_client_id
            )

        # Date range filtering
        if start_date:
            invoice_queryset = invoice_queryset.filter(created_at__gte=start_date)
            payment_queryset = payment_queryset.filter(created_at__gte=start_date)
        if end_date:
            invoice_queryset = invoice_queryset.filter(created_at__lte=end_date)
            payment_queryset = payment_queryset.filter(created_at__lte=end_date)

        # Invoice statistics
        invoice_stats = invoice_queryset.aggregate(
            total_invoices=Count("pk"),
            total_amount=Coalesce(Sum("total_amount"), Value(Decimal("0.00"))),
            total_paid=Coalesce(Sum("paid_amount"), Value(Decimal("0.00"))),
            pending_count=Count("pk", filter=Q(status="pending")),
            paid_count=Count("pk", filter=Q(status="paid")),
        )

        # Payment statistics
        payment_stats = payment_queryset.aggregate(
            total_payments=Count("pk"),
            total_collected=Coalesce(
                Sum("amount", filter=Q(status="completed")), Value(Decimal("0.00"))
            ),
            cash_payments=Count("pk", filter=Q(payment_method="cash")),
            card_payments=Count(
                "pk", filter=Q(payment_method__in=["credit_card", "debit_card"])
            ),
            online_payments=Count("pk", filter=Q(payment_method="online")),
        )

        # Calculate outstanding balance
        outstanding = invoice_stats["total_amount"] - invoice_stats["total_paid"]

        return {
            "invoices": invoice_stats,
            "payments": payment_stats,
            "outstanding_balance": outstanding,
        }

    @staticmethod
    def get_revenue_trends(
        lab_client_id=None, period="month", start_date=None, end_date=None
    ):
        """
        Get revenue trends over time.

        Args:
            lab_client_id: Filter by lab client
            period: Grouping period ('day', 'week', 'month')
            start_date: Start date for trend data
            end_date: End date for trend data

        Returns:
            list: Time-series revenue data
        """
        queryset = Payment.objects.filter(status="completed")

        # Multi-tenant filtering
        if lab_client_id:
            queryset = queryset.filter(invoice__lab_client_id=lab_client_id)

        # Default to last 6 months
        if not start_date:
            start_date = timezone.now() - timedelta(days=180)
        if not end_date:
            end_date = timezone.now()

        queryset = queryset.filter(created_at__gte=start_date, created_at__lte=end_date)

        # Group by period
        if period == "day":
            trunc_func = TruncDate
        elif period == "week":
            trunc_func = TruncWeek
        else:  # month
            trunc_func = TruncMonth

        trends = list(
            queryset.annotate(period=trunc_func("created_at"))
            .values("period")
            .annotate(
                revenue=Coalesce(Sum("amount"), Value(Decimal("0.00"))),
                payment_count=Count("pk"),
            )
            .order_by("period")
        )

        return trends

    @staticmethod
    def get_appointment_statistics(lab_client_id=None, start_date=None, end_date=None):
        """
        Get appointment statistics.

        Args:
            lab_client_id: Filter by lab client
            start_date: Filter appointments after this date
            end_date: Filter appointments before this date

        Returns:
            dict: Appointment statistics
        """
        queryset = Appointment.objects.all()

        # Multi-tenant filtering
        if lab_client_id:
            queryset = queryset.for_lab(lab_client_id)

        # Date range filtering
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)

        stats = queryset.aggregate(
            total=Count("pk"),
            scheduled=Count("pk", filter=Q(status="scheduled")),
            confirmed=Count("pk", filter=Q(status="confirmed")),
            in_progress=Count("pk", filter=Q(status="in_progress")),
            completed=Count("pk", filter=Q(status="completed")),
            cancelled=Count("pk", filter=Q(status="cancelled")),
            no_show=Count("pk", filter=Q(status="no_show")),
            checked_in=Count("pk", filter=Q(checked_in_at__isnull=False)),
        )

        # Calculate show rate (completed / (completed + no_show))
        total_concluded = stats["completed"] + stats["no_show"]
        show_rate = (
            (stats["completed"] / total_concluded * 100) if total_concluded > 0 else 0
        )

        stats["show_rate_percentage"] = round(show_rate, 2)

        return stats

    @staticmethod
    def get_user_statistics(lab_client_id=None):
        """
        Get user/patient statistics.

        Args:
            lab_client_id: Filter by lab client

        Returns:
            dict: User statistics by role
        """
        queryset = User.objects.filter(is_active=True)

        # Multi-tenant filtering (exclude admins who have no lab_client_id)
        if lab_client_id:
            queryset = queryset.filter(lab_client_id=lab_client_id)

        stats = queryset.aggregate(
            total_users=Count("pk"),
            patients=Count("pk", filter=Q(role="patient")),
            doctors=Count("pk", filter=Q(role="doctor")),
            lab_staff=Count("pk", filter=Q(role="lab_staff")),
            lab_managers=Count("pk", filter=Q(role="lab_manager")),
        )

        # Get new users this month
        month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0)
        new_this_month = queryset.filter(date_joined__gte=month_start).count()

        stats["new_this_month"] = new_this_month

        return stats

    @staticmethod
    def get_dashboard_summary(lab_client_id=None):
        """
        Get comprehensive dashboard summary for lab managers.

        Args:
            lab_client_id: Filter by lab client

        Returns:
            dict: Complete dashboard statistics
        """
        # Get current month date range
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0)

        return {
            "studies": StatisticsService.get_study_statistics(
                lab_client_id=lab_client_id,
                start_date=month_start,
            ),
            "revenue": StatisticsService.get_revenue_statistics(
                lab_client_id=lab_client_id,
                start_date=month_start,
            ),
            "appointments": StatisticsService.get_appointment_statistics(
                lab_client_id=lab_client_id,
                start_date=month_start,
            ),
            "users": StatisticsService.get_user_statistics(lab_client_id=lab_client_id),
            "period": {
                "start": month_start.isoformat(),
                "end": now.isoformat(),
                "label": "Current Month",
            },
        }

    @staticmethod
    def get_popular_practices(lab_client_id=None, limit=10):
        """
        Get most popular practices by order count.

        Args:
            lab_client_id: Filter by lab client
            limit: Number of top practices to return

        Returns:
            list: Practices with order counts
        """
        queryset = Study.objects.all()

        if lab_client_id:
            queryset = queryset.for_lab(lab_client_id)

        popular_practices = list(
            queryset.values(
                "practice__name",
                "practice__technique",
            )
            .annotate(
                order_count=Count("pk"),
                completed_count=Count("pk", filter=Q(status="completed")),
            )
            .order_by("-order_count")[:limit]
        )

        return popular_practices

    @staticmethod
    def get_top_revenue_practices(lab_client_id=None, limit=10):
        """
        Get practices generating most revenue.

        Args:
            lab_client_id: Filter by lab client
            limit: Number of top practices to return

        Returns:
            list: Practices with revenue totals
        """
        queryset = Invoice.objects.filter(status__in=["paid", "partially_paid"])

        if lab_client_id:
            queryset = queryset.for_lab(lab_client_id)

        # Join with studies to get practices
        top_revenue = list(
            queryset.filter(study__isnull=False)
            .values(
                "study__practice__name",
                "study__practice__technique",
            )
            .annotate(
                total_revenue=Coalesce(Sum("paid_amount"), Value(Decimal("0.00"))),
                order_count=Count("pk"),
            )
            .order_by("-total_revenue")[:limit]
        )

        return top_revenue

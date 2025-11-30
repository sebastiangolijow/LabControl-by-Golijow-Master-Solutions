"""API views for analytics app."""

from datetime import datetime

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import CanViewAnalytics
from .serializers import (
    AppointmentStatisticsSerializer,
    DashboardSummarySerializer,
    PopularStudyTypeSerializer,
    RevenueStatisticsSerializer,
    RevenueTrendSerializer,
    StudyStatisticsSerializer,
    StudyTrendSerializer,
    TopRevenueStudyTypeSerializer,
    UserStatisticsSerializer,
)
from .services import StatisticsService


class BaseAnalyticsView(APIView):
    """
    Base view for analytics endpoints.

    Handles common functionality like multi-tenant filtering.
    """

    permission_classes = [CanViewAnalytics]

    def get_lab_client_id(self, request):
        """
        Get lab_client_id for filtering.

        Admins can optionally filter by lab_client_id via query param.
        Lab managers are restricted to their own lab.

        Returns:
            int or None: lab_client_id for filtering
        """
        user = request.user

        # Admin can filter by lab_client_id or see all labs
        if user.role == "admin":
            lab_id = request.query_params.get("lab_client_id")
            return int(lab_id) if lab_id else None

        # Lab managers can only see their own lab
        return user.lab_client_id

    def get_date_range(self, request):
        """
        Extract start_date and end_date from query params.

        Returns:
            tuple: (start_date, end_date) or (None, None)
        """
        from django.utils import timezone

        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")

        start_date = None
        end_date = None

        if start_date_str:
            try:
                dt = datetime.fromisoformat(start_date_str)
                # Make timezone-aware if naive
                if dt.tzinfo is None:
                    start_date = timezone.make_aware(dt)
                else:
                    start_date = dt
            except ValueError:
                pass

        if end_date_str:
            try:
                dt = datetime.fromisoformat(end_date_str)
                # Make timezone-aware if naive
                if dt.tzinfo is None:
                    end_date = timezone.make_aware(dt)
                else:
                    end_date = dt
            except ValueError:
                pass

        return start_date, end_date


class DashboardSummaryView(BaseAnalyticsView):
    """
    GET /api/v1/analytics/dashboard/

    Get comprehensive dashboard summary with all key metrics.

    Query Parameters:
        - lab_client_id (admin only): Filter by lab client

    Returns:
        - studies: Study statistics for current month
        - revenue: Revenue statistics for current month
        - appointments: Appointment statistics for current month
        - users: User counts by role
        - period: Date range info
    """

    def get(self, request):
        """Get dashboard summary."""
        lab_client_id = self.get_lab_client_id(request)

        data = StatisticsService.get_dashboard_summary(lab_client_id=lab_client_id)

        serializer = DashboardSummarySerializer(data)
        return Response(serializer.data)


class StudyStatisticsView(BaseAnalyticsView):
    """
    GET /api/v1/analytics/studies/

    Get study statistics with optional date range filtering.

    Query Parameters:
        - lab_client_id (admin only): Filter by lab client
        - start_date: ISO format datetime (e.g., 2024-01-01)
        - end_date: ISO format datetime

    Returns:
        - overview: Counts by status
        - by_type: Breakdown by study type
        - avg_processing_hours: Average completion time
    """

    def get(self, request):
        """Get study statistics."""
        lab_client_id = self.get_lab_client_id(request)
        start_date, end_date = self.get_date_range(request)

        data = StatisticsService.get_study_statistics(
            lab_client_id=lab_client_id,
            start_date=start_date,
            end_date=end_date,
        )

        serializer = StudyStatisticsSerializer(data)
        return Response(serializer.data)


class StudyTrendsView(BaseAnalyticsView):
    """
    GET /api/v1/analytics/studies/trends/

    Get study trends over time.

    Query Parameters:
        - lab_client_id (admin only): Filter by lab client
        - period: Grouping period ('day', 'week', 'month') - default: 'month'
        - start_date: ISO format datetime
        - end_date: ISO format datetime

    Returns:
        List of time-series data with study counts by period
    """

    def get(self, request):
        """Get study trends."""
        lab_client_id = self.get_lab_client_id(request)
        start_date, end_date = self.get_date_range(request)
        period = request.query_params.get("period", "month")

        data = StatisticsService.get_study_trends(
            lab_client_id=lab_client_id,
            period=period,
            start_date=start_date,
            end_date=end_date,
        )

        serializer = StudyTrendSerializer(data, many=True)
        return Response(serializer.data)


class RevenueStatisticsView(BaseAnalyticsView):
    """
    GET /api/v1/analytics/revenue/

    Get revenue and payment statistics.

    Query Parameters:
        - lab_client_id (admin only): Filter by lab client
        - start_date: ISO format datetime
        - end_date: ISO format datetime

    Returns:
        - invoices: Invoice statistics
        - payments: Payment statistics
        - outstanding_balance: Total unpaid amount
    """

    def get(self, request):
        """Get revenue statistics."""
        lab_client_id = self.get_lab_client_id(request)
        start_date, end_date = self.get_date_range(request)

        data = StatisticsService.get_revenue_statistics(
            lab_client_id=lab_client_id,
            start_date=start_date,
            end_date=end_date,
        )

        serializer = RevenueStatisticsSerializer(data)
        return Response(serializer.data)


class RevenueTrendsView(BaseAnalyticsView):
    """
    GET /api/v1/analytics/revenue/trends/

    Get revenue trends over time.

    Query Parameters:
        - lab_client_id (admin only): Filter by lab client
        - period: Grouping period ('day', 'week', 'month') - default: 'month'
        - start_date: ISO format datetime
        - end_date: ISO format datetime

    Returns:
        List of time-series revenue data by period
    """

    def get(self, request):
        """Get revenue trends."""
        lab_client_id = self.get_lab_client_id(request)
        start_date, end_date = self.get_date_range(request)
        period = request.query_params.get("period", "month")

        data = StatisticsService.get_revenue_trends(
            lab_client_id=lab_client_id,
            period=period,
            start_date=start_date,
            end_date=end_date,
        )

        serializer = RevenueTrendSerializer(data, many=True)
        return Response(serializer.data)


class AppointmentStatisticsView(BaseAnalyticsView):
    """
    GET /api/v1/analytics/appointments/

    Get appointment statistics.

    Query Parameters:
        - lab_client_id (admin only): Filter by lab client
        - start_date: ISO format datetime
        - end_date: ISO format datetime

    Returns:
        Appointment counts by status and show rate percentage
    """

    def get(self, request):
        """Get appointment statistics."""
        lab_client_id = self.get_lab_client_id(request)
        start_date, end_date = self.get_date_range(request)

        data = StatisticsService.get_appointment_statistics(
            lab_client_id=lab_client_id,
            start_date=start_date,
            end_date=end_date,
        )

        serializer = AppointmentStatisticsSerializer(data)
        return Response(serializer.data)


class UserStatisticsView(BaseAnalyticsView):
    """
    GET /api/v1/analytics/users/

    Get user/patient statistics.

    Query Parameters:
        - lab_client_id (admin only): Filter by lab client

    Returns:
        User counts by role and new user count for current month
    """

    def get(self, request):
        """Get user statistics."""
        lab_client_id = self.get_lab_client_id(request)

        data = StatisticsService.get_user_statistics(lab_client_id=lab_client_id)

        serializer = UserStatisticsSerializer(data)
        return Response(serializer.data)


class PopularStudyTypesView(BaseAnalyticsView):
    """
    GET /api/v1/analytics/popular-study-types/

    Get most popular study types by order count.

    Query Parameters:
        - lab_client_id (admin only): Filter by lab client
        - limit: Number of results to return (default: 10)

    Returns:
        List of study types with order counts
    """

    def get(self, request):
        """Get popular study types."""
        lab_client_id = self.get_lab_client_id(request)
        limit = int(request.query_params.get("limit", 10))

        data = StatisticsService.get_popular_study_types(
            lab_client_id=lab_client_id,
            limit=limit,
        )

        serializer = PopularStudyTypeSerializer(data, many=True)
        return Response(serializer.data)


class TopRevenueStudyTypesView(BaseAnalyticsView):
    """
    GET /api/v1/analytics/top-revenue-study-types/

    Get study types generating most revenue.

    Query Parameters:
        - lab_client_id (admin only): Filter by lab client
        - limit: Number of results to return (default: 10)

    Returns:
        List of study types with revenue totals
    """

    def get(self, request):
        """Get top revenue study types."""
        lab_client_id = self.get_lab_client_id(request)
        limit = int(request.query_params.get("limit", 10))

        data = StatisticsService.get_top_revenue_study_types(
            lab_client_id=lab_client_id,
            limit=limit,
        )

        serializer = TopRevenueStudyTypeSerializer(data, many=True)
        return Response(serializer.data)

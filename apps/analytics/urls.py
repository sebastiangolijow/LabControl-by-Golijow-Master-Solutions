"""URL routing for analytics app."""

from django.urls import path

from .views import (
    AppointmentStatisticsView,
    DashboardSummaryView,
    PopularPracticesView,
    RevenueStatisticsView,
    RevenueTrendsView,
    StudyStatisticsView,
    StudyTrendsView,
    TopRevenuePracticesView,
    UserStatisticsView,
)

app_name = "analytics"

urlpatterns = [
    # Dashboard summary - comprehensive stats for current month
    path("dashboard/", DashboardSummaryView.as_view(), name="dashboard-summary"),
    # Study statistics
    path("studies/", StudyStatisticsView.as_view(), name="study-statistics"),
    path("studies/trends/", StudyTrendsView.as_view(), name="study-trends"),
    # Revenue statistics
    path("revenue/", RevenueStatisticsView.as_view(), name="revenue-statistics"),
    path("revenue/trends/", RevenueTrendsView.as_view(), name="revenue-trends"),
    # Appointment statistics
    path(
        "appointments/",
        AppointmentStatisticsView.as_view(),
        name="appointment-statistics",
    ),
    # User statistics
    path("users/", UserStatisticsView.as_view(), name="user-statistics"),
    # Practice analytics
    path(
        "popular-practices/",
        PopularPracticesView.as_view(),
        name="popular-practices",
    ),
    path(
        "top-revenue-practices/",
        TopRevenuePracticesView.as_view(),
        name="top-revenue-practices",
    ),
]

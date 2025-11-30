"""URL routing for analytics app."""

from django.urls import path

from .views import (
    AppointmentStatisticsView,
    DashboardSummaryView,
    PopularStudyTypesView,
    RevenueStatisticsView,
    RevenueTrendsView,
    StudyStatisticsView,
    StudyTrendsView,
    TopRevenueStudyTypesView,
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
    # Study type analytics
    path(
        "popular-study-types/",
        PopularStudyTypesView.as_view(),
        name="popular-study-types",
    ),
    path(
        "top-revenue-study-types/",
        TopRevenueStudyTypesView.as_view(),
        name="top-revenue-study-types",
    ),
]

"""Serializers for analytics app."""

from rest_framework import serializers


class StudyStatisticsSerializer(serializers.Serializer):
    """Serializer for study statistics response."""

    overview = serializers.DictField()
    by_practice = serializers.ListField()
    avg_processing_hours = serializers.FloatField(allow_null=True)


class StudyTrendSerializer(serializers.Serializer):
    """Serializer for study trend data."""

    period = serializers.DateTimeField()
    total = serializers.IntegerField()
    pending = serializers.IntegerField()
    in_progress = serializers.IntegerField()
    completed = serializers.IntegerField()


class RevenueStatisticsSerializer(serializers.Serializer):
    """Serializer for revenue statistics response."""

    invoices = serializers.DictField()
    payments = serializers.DictField()
    outstanding_balance = serializers.DecimalField(max_digits=10, decimal_places=2)


class RevenueTrendSerializer(serializers.Serializer):
    """Serializer for revenue trend data."""

    period = serializers.DateTimeField()
    revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    payment_count = serializers.IntegerField()


class AppointmentStatisticsSerializer(serializers.Serializer):
    """Serializer for appointment statistics response."""

    total = serializers.IntegerField()
    scheduled = serializers.IntegerField()
    confirmed = serializers.IntegerField()
    in_progress = serializers.IntegerField()
    completed = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    no_show = serializers.IntegerField()
    checked_in = serializers.IntegerField()
    show_rate_percentage = serializers.FloatField()


class UserStatisticsSerializer(serializers.Serializer):
    """Serializer for user statistics response."""

    total_users = serializers.IntegerField()
    patients = serializers.IntegerField()
    doctors = serializers.IntegerField()
    lab_staff = serializers.IntegerField()
    lab_managers = serializers.IntegerField()
    new_this_month = serializers.IntegerField()


class DashboardSummarySerializer(serializers.Serializer):
    """Serializer for complete dashboard summary."""

    studies = StudyStatisticsSerializer()
    revenue = RevenueStatisticsSerializer()
    appointments = AppointmentStatisticsSerializer()
    users = UserStatisticsSerializer()
    period = serializers.DictField()


class PopularPracticeSerializer(serializers.Serializer):
    """Serializer for popular practices."""

    practice__name = serializers.CharField()
    practice__technique = serializers.CharField()
    order_count = serializers.IntegerField()
    completed_count = serializers.IntegerField()


class TopRevenuePracticeSerializer(serializers.Serializer):
    """Serializer for top revenue practices."""

    study__practice__name = serializers.CharField()
    study__practice__technique = serializers.CharField()
    total_revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    order_count = serializers.IntegerField()

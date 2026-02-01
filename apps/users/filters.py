"""Filters for the users app."""

import django_filters
from django.db.models import Q

from .models import User


class UserFilter(django_filters.FilterSet):
    """Filter set for User model."""

    # Search across multiple fields
    search = django_filters.CharFilter(method="filter_search", label="Search")

    class Meta:
        model = User
        fields = {
            "role": ["exact"],
            "is_active": ["exact"],
            "lab_client_id": ["exact"],
        }

    def filter_search(self, queryset, name, value):
        """
        Filter users by search term across multiple fields.

        Searches in: first_name, last_name, email, dni
        """
        if not value:
            return queryset

        return queryset.filter(
            Q(first_name__icontains=value)
            | Q(last_name__icontains=value)
            | Q(email__icontains=value)
            | Q(dni__icontains=value)
        )

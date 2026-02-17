"""Filters for the studies app."""

import django_filters
from django.db.models import Q

from .models import Determination, Practice, Study


class StudyFilter(django_filters.FilterSet):
    """Filter set for Study model."""

    # Search across multiple fields
    search = django_filters.CharFilter(method="filter_search", label="Search")

    class Meta:
        model = Study
        fields = {
            "status": ["exact"],
            "practice": ["exact"],
            "patient": ["exact"],
            "ordered_by": ["exact"],
        }

    def filter_search(self, queryset, name, value):
        """
        Filter studies by search term across multiple fields.

        Searches in: protocol_number, patient name, practice name
        """
        if not value:
            return queryset

        return queryset.filter(
            Q(protocol_number__icontains=value)
            | Q(patient__first_name__icontains=value)
            | Q(patient__last_name__icontains=value)
            | Q(practice__name__icontains=value)
        )


class DeterminationFilter(django_filters.FilterSet):
    """Filter set for Determination model."""

    # Search across multiple fields
    search = django_filters.CharFilter(method="filter_search", label="Search")

    class Meta:
        model = Determination
        fields = {
            "is_active": ["exact"],
        }

    def filter_search(self, queryset, name, value):
        """
        Filter determinations by search term across multiple fields.

        Searches in: name, code, description
        """
        if not value:
            return queryset

        return queryset.filter(
            Q(name__icontains=value)
            | Q(code__icontains=value)
            | Q(description__icontains=value)
        )

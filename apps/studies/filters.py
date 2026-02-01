"""Filters for the studies app."""

import django_filters
from django.db.models import Q

from .models import Study


class StudyFilter(django_filters.FilterSet):
    """Filter set for Study model."""

    # Search across multiple fields
    search = django_filters.CharFilter(method="filter_search", label="Search")

    class Meta:
        model = Study
        fields = {
            "status": ["exact"],
            "study_type": ["exact"],
            "patient": ["exact"],
            "ordered_by": ["exact"],
        }

    def filter_search(self, queryset, name, value):
        """
        Filter studies by search term across multiple fields.

        Searches in: order_number, patient name, study type name
        """
        if not value:
            return queryset

        return queryset.filter(
            Q(order_number__icontains=value)
            | Q(patient__first_name__icontains=value)
            | Q(patient__last_name__icontains=value)
            | Q(study_type__name__icontains=value)
        )

"""Filters for the studies app."""

import django_filters

from apps.core.search import unaccent_icontains_q

from .models import Determination, Practice, Study


class StudyFilter(django_filters.FilterSet):
    """Filter set for Study model."""

    # Search across multiple fields. Accent- and case-insensitive.
    search = django_filters.CharFilter(method="filter_search", label="Search")
    practice = django_filters.UUIDFilter(
        field_name="study_practices__practice", label="Practice"
    )

    class Meta:
        model = Study
        fields = {
            # `in` lookup lets the frontend pass status__in=pending,in_progress
            # (used by the "upcoming studies" tab in ResultsView).
            "status": ["exact", "in"],
            "patient": ["exact"],
            "ordered_by": ["exact"],
        }

    def filter_search(self, queryset, name, value):
        """Filter studies by search term across multiple fields.

        Searches in: protocol_number, patient first/last name, patient dni,
        patient email, practice name. Accent- and case-insensitive.
        """
        if not value:
            return queryset

        return queryset.filter(
            unaccent_icontains_q(
                value,
                "protocol_number",
                "patient__first_name",
                "patient__last_name",
                "patient__dni",
                "patient__email",
                "study_practices__practice__name",
            )
        ).distinct()


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
        """Filter determinations by search term across multiple fields.

        Searches in: name, code, description. Accent- and case-insensitive.
        """
        return queryset.filter(
            unaccent_icontains_q(value, "name", "code", "description")
        )

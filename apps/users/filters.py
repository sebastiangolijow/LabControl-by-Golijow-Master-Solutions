"""Filters for the users app."""

import django_filters

from apps.core.search import unaccent_icontains_q

from .models import User


class UserFilter(django_filters.FilterSet):
    """Filter set for User model."""

    # Search across multiple fields. Accent- and case-insensitive
    # (e.g. "si" matches "Sí", "Asunción"; "muno" matches "Muñoz").
    search = django_filters.CharFilter(method="filter_search", label="Search")

    class Meta:
        model = User
        fields = {
            "role": ["exact"],
            "is_active": ["exact"],
            "lab_client_id": ["exact"],
        }

    def filter_search(self, queryset, name, value):
        """Filter users by search term across multiple fields.

        Searches in: first_name, last_name, email, dni, phone_number,
        matricula. Accent- and case-insensitive.
        """
        return queryset.filter(
            unaccent_icontains_q(
                value,
                "first_name",
                "last_name",
                "email",
                "dni",
                "phone_number",
                "matricula",
            )
        )

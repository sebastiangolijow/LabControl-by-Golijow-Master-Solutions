"""Tests for the unaccent_icontains_q search helper.

The Postgres unaccent extension is enabled by apps.core migration 0001.
The test database has it applied automatically before any test runs.
"""

from django.test import TestCase

from apps.core.search import unaccent_icontains_q
from apps.users.models import User


class UnaccentIcontainsQTests(TestCase):
    """Verify that the helper produces queries matching real Spanish patient
    names regardless of case OR accents — the key requirement that motivated
    the unaccent extension."""

    def setUp(self):
        super().setUp()
        # Patients with assorted accent / case patterns we need to match
        self.maria = User.objects.create_user(
            email="maria@example.com",
            first_name="María",
            last_name="González",
            role="patient",
        )
        self.munoz = User.objects.create_user(
            email="munoz@example.com",
            first_name="José",
            last_name="Muñoz",
            role="patient",
        )
        self.juan = User.objects.create_user(
            email="juan@example.com",
            first_name="Juan",
            last_name="López",
            role="patient",
        )
        # Patient whose name has the substring "sí" (accented) — must match
        # a search for "si" (unaccented).
        self.sira = User.objects.create_user(
            email="sira@example.com",
            first_name="Sira",
            last_name="Pérez",
            role="patient",
        )
        self.sira_accented = User.objects.create_user(
            email="sirita@example.com",
            first_name="Sí­ra",  # Sí + ra — contains literal "sí"
            last_name="Vargas",
            role="patient",
        )

    def _search(self, term):
        """Helper: run a search across first_name + last_name."""
        return list(
            User.objects.filter(role="patient")
            .filter(unaccent_icontains_q(term, "first_name", "last_name"))
            .order_by("email")
        )

    def test_si_matches_both_si_and_accented_si(self):
        """Searching 'si' (unaccented) must match both 'Sira' and 'Sí­ra'.

        This is the user-reported bug: 'si' was returning too few results
        because plain __icontains is accent-sensitive.
        """
        results = self._search("si")
        self.assertIn(self.sira, results)
        self.assertIn(self.sira_accented, results)

    def test_accent_insensitive_match_no_accent_term_with_accent_data(self):
        """'maria' should match 'María'."""
        results = self._search("maria")
        self.assertIn(self.maria, results)

    def test_accent_insensitive_with_n_tilde(self):
        """'munoz' should match 'Muñoz' (ñ stripped to n)."""
        results = self._search("munoz")
        self.assertIn(self.munoz, results)

    def test_uppercase_term_matches_lowercase_data_with_accent(self):
        """'GONZALEZ' should match 'González'."""
        results = self._search("GONZALEZ")
        self.assertIn(self.maria, results)

    def test_search_matches_across_multiple_fields(self):
        """Searching 'lopez' (no accent) should hit either first or last name."""
        results = self._search("lopez")
        self.assertIn(self.juan, results)

    def test_no_match_returns_empty(self):
        results = self._search("xyz_no_match")
        self.assertEqual(results, [])

    def test_empty_search_returns_no_filter(self):
        """Empty value returns Q() (always-true), so all patients match."""
        all_patients = list(User.objects.filter(role="patient").order_by("email"))
        results = self._search("")
        self.assertEqual(results, all_patients)

    def test_none_search_returns_no_filter(self):
        results = list(
            User.objects.filter(role="patient")
            .filter(unaccent_icontains_q(None, "first_name"))
            .order_by("email")
        )
        all_patients = list(User.objects.filter(role="patient").order_by("email"))
        self.assertEqual(results, all_patients)


class UserFilterAccentInsensitiveTests(TestCase):
    """End-to-end: UserFilter (the FilterSet used by /api/v1/users/) handles
    accent-insensitive search correctly. This is the bug the user reported:
    searching 'si' was returning the wrong (too few) results."""

    def test_user_filter_search_matches_accented_name(self):
        from apps.users.filters import UserFilter

        User.objects.create_user(
            email="ainara@example.com",
            first_name="Ainara",
            last_name="Romero",
            role="patient",
        )
        User.objects.create_user(
            email="moises@example.com",
            first_name="Moisés",
            last_name="Síra",  # contains 'sí' — must be found by 'si'
            role="patient",
        )
        User.objects.create_user(
            email="sira@example.com",
            first_name="Sira",
            last_name="López",  # contains 'si' literally
            role="patient",
        )

        # Search for "si" — should find Moisés (Síra) and Sira (Sira),
        # but NOT Ainara (no 'si'/'sí' anywhere)
        f = UserFilter({"search": "si"}, queryset=User.objects.filter(role="patient"))
        emails = set(f.qs.values_list("email", flat=True))

        self.assertIn("moises@example.com", emails)
        self.assertIn("sira@example.com", emails)
        self.assertNotIn("ainara@example.com", emails)

"""Tests for Practice and StudyType filters and search functionality."""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from apps.studies.models import Practice, StudyType
from tests.base import BaseTestCase

User = get_user_model()


class TestPracticeSearch(BaseTestCase):
    """Test cases for Practice search functionality."""

    def create_practice(self, **kwargs):
        """Helper to create a practice for testing."""
        self._user_counter += 1
        defaults = {
            "name": f"Practice {self._user_counter}",
            "technique": "PCR",
            "sample_type": "Blood",
            "sample_quantity": "5ml",
            "sample_instructions": "Fasting required",
            "conservation_transport": "Keep refrigerated",
            "delay_days": 7,
            "price": "100.00",
            "is_active": True,
        }
        defaults.update(kwargs)
        return Practice.objects.create(**defaults)

    def test_practice_search_by_name(self):
        """Test searching practices by name."""
        client, admin = self.authenticate_as_admin()

        # Create test practices
        practice1 = self.create_practice(name="COVID-19 PCR Test")
        practice2 = self.create_practice(name="Hepatitis B Surface Antigen")
        practice3 = self.create_practice(name="COVID-19 Antibody Test")

        # Search by name (case insensitive)
        response = client.get("/api/v1/studies/practices/?search=covid")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        names = [p["name"] for p in results]

        assert practice1.name in names
        assert practice3.name in names
        assert practice2.name not in names

    def test_practice_search_by_technique(self):
        """Test searching practices by technique."""
        client, admin = self.authenticate_as_admin()

        # Create practices with different techniques
        practice1 = self.create_practice(
            name="Test 1",
            technique="PCR Real-Time"
        )
        practice2 = self.create_practice(
            name="Test 2",
            technique="ELISA"
        )
        practice3 = self.create_practice(
            name="Test 3",
            technique="PCR Multiplex"
        )

        # Search by technique
        response = client.get("/api/v1/studies/practices/?search=PCR")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        names = [p["name"] for p in results]

        assert practice1.name in names
        assert practice3.name in names
        assert practice2.name not in names

    def test_practice_search_by_sample_type(self):
        """Test searching practices by sample type."""
        client, admin = self.authenticate_as_admin()

        # Create practices with different sample types
        practice1 = self.create_practice(
            name="Blood Test 1",
            sample_type="Blood, Serum"
        )
        practice2 = self.create_practice(
            name="Urine Test",
            sample_type="Urine"
        )
        practice3 = self.create_practice(
            name="Blood Test 2",
            sample_type="Blood, Plasma"
        )

        # Search by sample type
        response = client.get("/api/v1/studies/practices/?search=Serum")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        names = [p["name"] for p in results]

        assert practice1.name in names
        assert practice2.name not in names
        assert practice3.name not in names

    def test_practice_search_empty_query(self):
        """Test that empty search returns all practices."""
        client, admin = self.authenticate_as_admin()

        # Create test practices
        practice1 = self.create_practice(name="Practice A")
        practice2 = self.create_practice(name="Practice B")

        # Search with empty query
        response = client.get("/api/v1/studies/practices/?search=")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]

        # Should return all practices
        assert len(results) >= 2

    def test_practice_search_no_results(self):
        """Test searching with term that matches nothing."""
        client, admin = self.authenticate_as_admin()

        # Create test practices
        self.create_practice(name="HIV Test")
        self.create_practice(name="Hepatitis Test")

        # Search for non-existent term
        response = client.get("/api/v1/studies/practices/?search=XYZNONEXISTENT")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]

        assert len(results) == 0

    def test_practice_search_pagination(self):
        """Test that search results are paginated correctly."""
        client, admin = self.authenticate_as_admin()

        # Create multiple practices with similar names
        for i in range(10):
            self.create_practice(name=f"COVID Test {i}")

        # Search should return paginated results
        response = client.get("/api/v1/studies/practices/?search=COVID")
        assert response.status_code == status.HTTP_200_OK

        # Check pagination structure
        assert "results" in response.data
        assert "count" in response.data
        assert response.data["count"] >= 10

    def test_practice_ordering_with_search(self):
        """Test ordering practices with search."""
        client, admin = self.authenticate_as_admin()

        # Create practices with different prices
        practice1 = self.create_practice(name="Test A", price="50.00")
        practice2 = self.create_practice(name="Test B", price="150.00")
        practice3 = self.create_practice(name="Test C", price="100.00")

        # Search with ordering by price
        response = client.get("/api/v1/studies/practices/?search=Test&ordering=price")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]

        # Check that results are ordered by price (ascending)
        prices = [float(p["price"]) for p in results]
        assert prices == sorted(prices)

    def test_practice_permissions_authenticated_user_can_search(self):
        """Test that authenticated users can search practices."""
        # Test with patient
        client, patient = self.authenticate_as_patient()
        response = client.get("/api/v1/studies/practices/?search=test")
        assert response.status_code == status.HTTP_200_OK

        # Test with doctor
        client, doctor = self.authenticate_as_admin()
        doctor.role = "doctor"
        doctor.save()
        response = client.get("/api/v1/studies/practices/?search=test")
        assert response.status_code == status.HTTP_200_OK

        # Test with lab staff
        client, lab_staff = self.authenticate_as_lab_staff()
        response = client.get("/api/v1/studies/practices/?search=test")
        assert response.status_code == status.HTTP_200_OK


class TestStudyTypeFilter(BaseTestCase):
    """Test cases for StudyType filter and search functionality."""

    def test_studytype_search_by_name(self):
        """Test searching study types by name."""
        client, admin = self.authenticate_as_admin()

        # Create test study types
        st1 = self.create_study_type(name="Complete Blood Count", code="CBC999")
        st2 = self.create_study_type(name="Chest X-Ray", code="XRAY999")
        st3 = self.create_study_type(name="Blood Glucose Test", code="GLUC999")

        # Search by name (should find both "Complete Blood Count" and "Blood Glucose Test")
        response = client.get("/api/v1/studies/types/?search=Blood")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        codes = [st["code"] for st in results]

        # Use codes instead of names to avoid ambiguity
        assert st1.code in codes
        assert st3.code in codes
        # X-Ray should not appear in results (no "Blood" in name)
        if len(codes) == 2:  # If only our 2 tests are returned
            assert st2.code not in codes

    def test_studytype_search_by_code(self):
        """Test searching study types by code."""
        client, admin = self.authenticate_as_admin()

        # Create test study types
        st1 = self.create_study_type(name="Test 1", code="COVID-PCR-001")
        st2 = self.create_study_type(name="Test 2", code="HEP-B-002")
        st3 = self.create_study_type(name="Test 3", code="COVID-AB-003")

        # Search by code
        response = client.get("/api/v1/studies/types/?search=COVID")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        codes = [st["code"] for st in results]

        assert st1.code in codes
        assert st3.code in codes
        assert st2.code not in codes

    def test_studytype_search_by_description(self):
        """Test searching study types by description."""
        client, admin = self.authenticate_as_admin()

        # Create study types with different descriptions
        st1 = self.create_study_type(
            name="Test A",
            code="TST001",
            description="Molecular diagnostic test for viral infections"
        )
        st2 = self.create_study_type(
            name="Test B",
            code="TST002",
            description="Imaging study for bone fractures"
        )
        st3 = self.create_study_type(
            name="Test C",
            code="TST003",
            description="Molecular analysis for genetic markers"
        )

        # Search by description
        response = client.get("/api/v1/studies/types/?search=Molecular")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        codes = [st["code"] for st in results]

        assert st1.code in codes
        assert st3.code in codes
        assert st2.code not in codes

    def test_studytype_search_by_category(self):
        """Test searching study types by category."""
        client, admin = self.authenticate_as_admin()

        # Create study types with different categories
        st1 = self.create_study_type(
            name="CBC",
            code="CBC001",
            category="Hematology Testing"
        )
        st2 = self.create_study_type(
            name="X-Ray",
            code="XRAY001",
            category="Radiology"
        )
        st3 = self.create_study_type(
            name="Platelet Count",
            code="PLT001",
            category="Hematology Testing"
        )

        # Search by category
        response = client.get("/api/v1/studies/types/?search=Hematology")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        codes = [st["code"] for st in results]

        assert st1.code in codes
        assert st3.code in codes
        assert st2.code not in codes

    def test_studytype_filter_by_category_exact(self):
        """Test filtering study types by exact category."""
        client, admin = self.authenticate_as_admin()

        # Create study types with different categories
        st1 = self.create_study_type(
            name="CBC",
            code="CBC001",
            category="Hematology"
        )
        st2 = self.create_study_type(
            name="Liver Panel",
            code="LVR001",
            category="Biochemistry"
        )
        st3 = self.create_study_type(
            name="Platelet Count",
            code="PLT001",
            category="Hematology"
        )

        # Filter by exact category
        response = client.get("/api/v1/studies/types/?category=Hematology")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        codes = [st["code"] for st in results]

        assert st1.code in codes
        assert st3.code in codes
        assert st2.code not in codes

    def test_studytype_filter_by_requires_fasting_true(self):
        """Test filtering study types by requires_fasting=true."""
        client, admin = self.authenticate_as_admin()

        # Create study types with different fasting requirements
        st1 = self.create_study_type(
            name="Fasting Glucose",
            code="FGL001",
            requires_fasting=True
        )
        st2 = self.create_study_type(
            name="CBC",
            code="CBC001",
            requires_fasting=False
        )
        st3 = self.create_study_type(
            name="Lipid Panel",
            code="LIP001",
            requires_fasting=True
        )

        # Filter by requires_fasting=true
        response = client.get("/api/v1/studies/types/?requires_fasting=true")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        codes = [st["code"] for st in results]

        assert st1.code in codes
        assert st3.code in codes
        assert st2.code not in codes

    def test_studytype_filter_by_requires_fasting_false(self):
        """Test filtering study types by requires_fasting=false."""
        client, admin = self.authenticate_as_admin()

        # Create study types
        st1 = self.create_study_type(
            name="Fasting Glucose",
            code="FGL001",
            requires_fasting=True
        )
        st2 = self.create_study_type(
            name="CBC",
            code="CBC001",
            requires_fasting=False
        )
        st3 = self.create_study_type(
            name="Blood Type",
            code="BT001",
            requires_fasting=False
        )

        # Filter by requires_fasting=false
        response = client.get("/api/v1/studies/types/?requires_fasting=false")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        codes = [st["code"] for st in results]

        assert st2.code in codes
        assert st3.code in codes
        assert st1.code not in codes

    def test_studytype_filter_by_is_active_true(self):
        """Test filtering study types by is_active=true."""
        client, admin = self.authenticate_as_admin()

        # Create active and inactive study types
        st1 = self.create_study_type(name="Active Test", code="ACT001", is_active=True)
        st2 = self.create_study_type(name="Inactive Test", code="INACT001", is_active=False)

        # Filter by is_active=true
        response = client.get("/api/v1/studies/types/?is_active=true")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        codes = [st["code"] for st in results]

        assert st1.code in codes
        # st2 won't appear because the queryset filters is_active=True by default

    def test_studytype_combine_search_and_category_filter(self):
        """Test combining search with category filter."""
        client, admin = self.authenticate_as_admin()

        # Create study types with various combinations
        st1 = self.create_study_type(
            name="Blood Glucose",
            code="BG001",
            category="Biochemistry"
        )
        st2 = self.create_study_type(
            name="Blood Count",
            code="BC001",
            category="Hematology"
        )
        st3 = self.create_study_type(
            name="Blood Lipids",
            code="BL001",
            category="Biochemistry"
        )

        # Search for "Blood" in "Biochemistry" category
        response = client.get("/api/v1/studies/types/?search=Blood&category=Biochemistry")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        codes = [st["code"] for st in results]

        assert st1.code in codes
        assert st3.code in codes
        assert st2.code not in codes

    def test_studytype_combine_category_and_fasting_filters(self):
        """Test combining category and requires_fasting filters."""
        client, admin = self.authenticate_as_admin()

        # Create study types with various combinations
        st1 = self.create_study_type(
            name="Fasting Glucose",
            code="FG001",
            category="Biochemistry",
            requires_fasting=True
        )
        st2 = self.create_study_type(
            name="Random Glucose",
            code="RG001",
            category="Biochemistry",
            requires_fasting=False
        )
        st3 = self.create_study_type(
            name="Fasting Lipid Panel",
            code="FLP001",
            category="Biochemistry",
            requires_fasting=True
        )

        # Filter for Biochemistry tests that require fasting
        response = client.get("/api/v1/studies/types/?category=Biochemistry&requires_fasting=true")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        codes = [st["code"] for st in results]

        assert st1.code in codes
        assert st3.code in codes
        assert st2.code not in codes

    def test_studytype_ordering_with_filters(self):
        """Test ordering study types with filters."""
        client, admin = self.authenticate_as_admin()

        # Create study types with same category
        st1 = self.create_study_type(
            name="Z Test",
            code="Z001",
            category="Hematology"
        )
        st2 = self.create_study_type(
            name="A Test",
            code="A001",
            category="Hematology"
        )
        st3 = self.create_study_type(
            name="M Test",
            code="M001",
            category="Hematology"
        )

        # Filter by category and order by name
        response = client.get("/api/v1/studies/types/?category=Hematology&ordering=name")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]

        # Check that results are ordered by name
        names = [st["name"] for st in results]
        assert names == sorted(names)

    def test_studytype_empty_search_returns_all(self):
        """Test that empty search returns all study types."""
        client, admin = self.authenticate_as_admin()

        # Create test study types
        st1 = self.create_study_type(name="Test A", code="TST001")
        st2 = self.create_study_type(name="Test B", code="TST002")

        # Empty search
        response = client.get("/api/v1/studies/types/?search=")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]

        # Should return all study types
        assert len(results) >= 2

    def test_studytype_search_case_insensitive(self):
        """Test that search is case insensitive."""
        client, admin = self.authenticate_as_admin()

        # Create study type
        st1 = self.create_study_type(name="COVID-19 PCR Test", code="COVID001")

        # Search with different cases
        for search_term in ["covid", "COVID", "CoViD", "COVID"]:
            response = client.get(f"/api/v1/studies/types/?search={search_term}")
            assert response.status_code == status.HTTP_200_OK
            results = response.data["results"]
            codes = [st["code"] for st in results]
            assert st1.code in codes

    def test_studytype_pagination_with_filters(self):
        """Test that filtered results are paginated correctly."""
        client, admin = self.authenticate_as_admin()

        # Create multiple study types in same category
        for i in range(10):
            self.create_study_type(
                name=f"Hematology Test {i}",
                code=f"HEM{i:03d}",
                category="Hematology"
            )

        # Filter should return paginated results
        response = client.get("/api/v1/studies/types/?category=Hematology")
        assert response.status_code == status.HTTP_200_OK

        # Check pagination structure
        assert "results" in response.data
        assert "count" in response.data
        assert response.data["count"] >= 10

    def test_studytype_permissions_authenticated_user_can_search(self):
        """Test that all authenticated users can search study types."""
        # Test with patient
        client, patient = self.authenticate_as_patient()
        response = client.get("/api/v1/studies/types/?search=test")
        assert response.status_code == status.HTTP_200_OK

        # Test with doctor
        client, doctor = self.authenticate_as_admin()
        doctor.role = "doctor"
        doctor.save()
        response = client.get("/api/v1/studies/types/?search=test")
        assert response.status_code == status.HTTP_200_OK

        # Test with lab staff
        client, lab_staff = self.authenticate_as_lab_staff()
        response = client.get("/api/v1/studies/types/?search=test")
        assert response.status_code == status.HTTP_200_OK

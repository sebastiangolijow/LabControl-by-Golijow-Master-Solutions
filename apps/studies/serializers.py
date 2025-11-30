"""Serializers for studies app."""

from rest_framework import serializers

from .models import Study, StudyType


class StudyTypeSerializer(serializers.ModelSerializer):
    """Serializer for StudyType model."""

    class Meta:
        model = StudyType
        fields = "__all__"


class StudySerializer(serializers.ModelSerializer):
    """Serializer for Study model."""

    study_type_detail = StudyTypeSerializer(source="study_type", read_only=True)
    patient_email = serializers.EmailField(source="patient.email", read_only=True)

    class Meta:
        model = Study
        fields = [
            "id",
            "order_number",
            "patient",
            "patient_email",
            "study_type",
            "study_type_detail",
            "ordered_by",
            "status",
            "sample_id",
            "sample_collected_at",
            "results",
            "results_file",
            "completed_at",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

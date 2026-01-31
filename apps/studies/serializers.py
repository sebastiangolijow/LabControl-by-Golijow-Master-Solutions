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
    ordered_by_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Study
        fields = [
            "id",
            "uuid",
            "order_number",
            "patient",
            "patient_email",
            "study_type",
            "study_type_detail",
            "ordered_by",
            "ordered_by_name",
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
        read_only_fields = ["uuid", "order_number", "created_at", "updated_at"]

    def get_ordered_by_name(self, obj):
        """Get the full name of the doctor who ordered the study."""
        if obj.ordered_by:
            return obj.ordered_by.get_full_name()
        return None


class StudyResultUploadSerializer(serializers.ModelSerializer):
    """Serializer for uploading study results."""

    results_file = serializers.FileField(required=True)
    results = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Study
        fields = ["results_file", "results"]

    def validate_results_file(self, value):
        """Validate file size and type."""
        # Max file size: 10MB
        max_size = 10 * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError("File size cannot exceed 10MB.")

        # Allowed file types
        allowed_types = ["application/pdf", "image/jpeg", "image/png"]
        if value.content_type not in allowed_types:
            raise serializers.ValidationError(
                "Only PDF, JPEG, and PNG files are allowed."
            )

        return value

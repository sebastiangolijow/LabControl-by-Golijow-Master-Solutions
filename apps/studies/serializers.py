"""Serializers for studies app."""

from rest_framework import serializers

from .models import Practice, Study, StudyType


class PracticeSerializer(serializers.ModelSerializer):
    """Serializer for Practice model."""

    class Meta:
        model = Practice
        fields = [
            "id",
            "uuid",
            "name",
            "technique",
            "sample_type",
            "sample_quantity",
            "sample_instructions",
            "conservation_transport",
            "delay_days",
            "price",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]


class StudyTypeSerializer(serializers.ModelSerializer):
    """Serializer for StudyType model."""

    practices_detail = PracticeSerializer(source="practices", many=True, read_only=True)
    practice_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Practice.objects.all(),
        source="practices",
        write_only=True,
        required=False,
    )

    class Meta:
        model = StudyType
        fields = [
            "id",
            "uuid",
            "name",
            "code",
            "description",
            "category",
            "requires_fasting",
            "preparation_instructions",
            "estimated_processing_hours",
            "practices",
            "practices_detail",
            "practice_ids",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]


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


class StudyCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new study."""

    class Meta:
        model = Study
        fields = [
            "study_type",
            "patient",
            "ordered_by",
            "order_number",
            "notes",
        ]

    def validate_order_number(self, value):
        """Ensure order number is unique."""
        if Study.objects.filter(order_number=value).exists():
            raise serializers.ValidationError(
                "A study with this order number already exists."
            )
        return value


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

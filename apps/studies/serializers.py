"""Serializers for studies app."""

from django.conf import settings
from rest_framework import serializers

from .models import Determination, Practice, Study, UserDetermination


class DeterminationSerializer(serializers.ModelSerializer):
    """Serializer for Determination model."""

    class Meta:
        model = Determination
        fields = [
            "id",
            "uuid",
            "name",
            "code",
            "unit",
            "reference_range",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]


class PracticeSerializer(serializers.ModelSerializer):
    """Serializer for Practice model."""

    determinations_detail = DeterminationSerializer(
        source="determinations", many=True, read_only=True
    )
    determination_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Determination.objects.all(),
        source="determinations",
        write_only=True,
        required=False,
    )

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
            "determinations",
            "determinations_detail",
            "determination_ids",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]


class UserDeterminationSerializer(serializers.ModelSerializer):
    """Serializer for UserDetermination model."""

    determination_detail = DeterminationSerializer(
        source="determination", read_only=True
    )

    class Meta:
        model = UserDetermination
        fields = [
            "id",
            "uuid",
            "study",
            "determination",
            "determination_detail",
            "value",
            "is_abnormal",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]


class StudySerializer(serializers.ModelSerializer):
    """Serializer for Study model."""

    practice_detail = PracticeSerializer(source="practice", read_only=True)
    patient_email = serializers.EmailField(source="patient.email", read_only=True)
    patient_name = serializers.SerializerMethodField(read_only=True)
    ordered_by_name = serializers.SerializerMethodField(read_only=True)
    determination_results = UserDeterminationSerializer(many=True, read_only=True)

    class Meta:
        model = Study
        fields = [
            "id",
            "uuid",
            "protocol_number",
            "patient",
            "patient_email",
            "patient_name",
            "practice",
            "practice_detail",
            "ordered_by",
            "ordered_by_name",
            "status",
            "solicited_date",
            "sample_id",
            "sample_collected_at",
            "results",
            "results_file",
            "determination_results",
            "completed_at",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "protocol_number", "created_at", "updated_at"]

    def get_patient_name(self, obj):
        """Get the full name of the patient."""
        return obj.patient.get_full_name() if obj.patient else None

    def get_ordered_by_name(self, obj):
        """Get the full name of the doctor who ordered the study."""
        if obj.ordered_by:
            return obj.ordered_by.get_full_name()
        return None


class StudyCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a new study.

    Supports creating a study with or without a results file in a single request.
    - If results_file is provided → status is set to 'completed' by the view.
    - If no results_file → status defaults to 'pending'.
    """

    results_file = serializers.FileField(required=False, allow_null=True)

    class Meta:
        model = Study
        fields = [
            "practice",
            "patient",
            "ordered_by",
            "protocol_number",
            "solicited_date",
            "sample_collected_at",
            "results_file",
            "results",
            "notes",
        ]

    def validate_protocol_number(self, value):
        """Ensure protocol number is unique."""
        if Study.objects.filter(protocol_number=value).exists():
            raise serializers.ValidationError(
                "A study with this protocol number already exists."
            )
        return value

    def validate_results_file(self, value):
        """Validate file size and type (same rules as upload serializer)."""
        if value is None:
            return value
        max_size = 10 * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError("File size cannot exceed 10MB.")
        allowed_types = ["application/pdf", "image/jpeg", "image/png"]
        if value.content_type not in allowed_types:
            raise serializers.ValidationError(
                "Only PDF, JPEG, and PNG files are allowed."
            )
        return value


class StudyResultUploadSerializer(serializers.ModelSerializer):
    """Serializer for uploading study results."""

    results_file = serializers.FileField(required=True)
    results = serializers.CharField(required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Import User model dynamically to avoid circular imports
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.fields["ordered_by"] = serializers.PrimaryKeyRelatedField(
            queryset=User.objects.filter(role="doctor"),
            required=False,
            allow_null=True,
        )

    class Meta:
        model = Study
        fields = ["results_file", "results", "ordered_by"]

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


class UserDeterminationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating user determination results."""

    class Meta:
        model = UserDetermination
        fields = [
            "study",
            "determination",
            "value",
            "is_abnormal",
            "notes",
        ]

    def validate(self, data):
        """Ensure the determination belongs to the practice of the study."""
        study = data.get("study")
        determination = data.get("determination")

        if study and determination:
            # Check if the determination is part of the practice
            if not study.practice.determinations.filter(id=determination.id).exists():
                raise serializers.ValidationError(
                    {
                        "determination": "This determination is not part of the study's practice."
                    }
                )

        return data

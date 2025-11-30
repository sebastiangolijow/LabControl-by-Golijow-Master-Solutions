"""Serializers for users app."""

from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model."""

    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "uuid",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "role",
            "lab_client_id",
            "is_verified",
            "date_joined",
        ]
        read_only_fields = ["id", "uuid", "date_joined", "is_verified"]


class UserDetailSerializer(UserSerializer):
    """Detailed serializer for User model (includes more information)."""

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + [
            "is_active",
            "last_login",
            "updated_at",
        ]


class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new users."""

    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            "email",
            "password",
            "password_confirm",
            "first_name",
            "last_name",
            "phone_number",
            "role",
        ]

    def validate(self, attrs):
        """Validate password confirmation."""
        if attrs.get("password") != attrs.get("password_confirm"):
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        attrs.pop("password_confirm")
        return attrs

    def create(self, validated_data):
        """Create user with encrypted password."""
        password = validated_data.pop("password")
        user = User.objects.create_user(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user information."""

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "phone_number",
        ]


class PatientRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for patient self-registration."""

    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            "email",
            "password",
            "password_confirm",
            "first_name",
            "last_name",
            "phone_number",
            "lab_client_id",
        ]

    def validate(self, attrs):
        """Validate password confirmation and set role to patient."""
        if attrs.get("password") != attrs.get("password_confirm"):
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        attrs.pop("password_confirm")

        # Force role to patient for public registration
        attrs["role"] = "patient"

        return attrs

    def create(self, validated_data):
        """Create patient user with encrypted password."""
        password = validated_data.pop("password")
        user = User.objects.create_user(**validated_data)
        user.set_password(password)
        user.save()

        # TODO: Send verification email
        # send_verification_email.delay(user.id)

        return user

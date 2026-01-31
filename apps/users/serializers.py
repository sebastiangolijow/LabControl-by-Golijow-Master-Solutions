"""Serializers for users app."""

from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model."""

    full_name = serializers.CharField(source="get_full_name", read_only=True)
    # Since uuid is the primary key, Django REST Framework will automatically
    # expose it as both 'id' and 'uuid' in the JSON response
    id = serializers.UUIDField(source="pk", read_only=True)

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
            "dni",
            "birthday",
            "profile_picture",
            "language",
            "gender",
            "location",
            "direction",
            "mutual_code",
            "mutual_name",
            "carnet",
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
            "dni",
            "birthday",
            "gender",
            "location",
            "direction",
            "mutual_code",
            "mutual_name",
            "carnet",
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
            "dni",
            "birthday",
            "profile_picture",
            "language",
            "gender",
            "location",
            "direction",
            "mutual_code",
            "mutual_name",
            "carnet",
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
            "dni",
            "birthday",
            "gender",
            "location",
            "direction",
            "mutual_code",
            "mutual_name",
            "carnet",
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

        # Note: Email verification is now triggered in PatientRegistrationView
        # to ensure it happens after successful response to user

        return user


class AdminUserCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for admin-created users (admin, doctor, patient).

    Users created by admins will receive an email to set their password.
    No password field is required here.
    """

    class Meta:
        model = User
        fields = [
            "email",
            "role",
            "first_name",
            "last_name",
            "phone_number",
            "dni",
            "birthday",
            "gender",
            "location",
            "direction",
            "mutual_code",
            "mutual_name",
            "carnet",
            "lab_client_id",
        ]

    def validate_role(self, value):
        """Validate that only allowed roles can be created."""
        allowed_roles = ["admin", "doctor", "patient"]
        if value not in allowed_roles:
            raise serializers.ValidationError(
                f"Invalid role. Allowed roles: {', '.join(allowed_roles)}"
            )
        return value

    def create(self, validated_data):
        """
        Create user without password.

        User will receive an email with a link to set their password.
        """
        import secrets

        # Generate a temporary password (will be replaced when user sets their own)
        temp_password = secrets.token_urlsafe(32)

        # Create user
        user = User.objects.create_user(**validated_data)
        user.set_password(temp_password)
        user.is_active = True  # User can login after setting password
        user.save()

        # Generate verification token for password setup
        user.generate_verification_token()

        # Track who created this user (set in view)
        if "created_by" in self.context:
            user.created_by = self.context["created_by"]
            user.save(update_fields=["created_by"])

        return user

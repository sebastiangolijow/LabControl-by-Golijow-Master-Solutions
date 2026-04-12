"""Serializers for users app."""

from dj_rest_auth.registration.serializers import RegisterSerializer
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
            "matricula",
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
            "matricula",
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
            "matricula",
        ]


class CustomRegisterSerializer(RegisterSerializer):
    """
    Custom registration serializer for dj-rest-auth.

    Overrides the default to remove username field and add patient-specific fields.
    """

    # Remove username field
    username = None

    # Add custom fields required for patients
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    phone_number = serializers.CharField(required=True)
    dni = serializers.CharField(required=True)
    birthday = serializers.DateField(required=True)
    gender = serializers.CharField(required=False, allow_blank=True)
    location = serializers.CharField(required=False, allow_blank=True)
    direction = serializers.CharField(required=False, allow_blank=True)
    mutual_code = serializers.IntegerField(required=False, allow_null=True)
    mutual_name = serializers.CharField(required=False, allow_blank=True)
    carnet = serializers.CharField(required=False, allow_blank=True)
    lab_client_id = serializers.IntegerField(required=False, allow_null=True)

    def get_cleaned_data(self):
        """Return cleaned data including custom fields."""
        data = super().get_cleaned_data()
        data.update({
            'first_name': self.validated_data.get('first_name', ''),
            'last_name': self.validated_data.get('last_name', ''),
            'phone_number': self.validated_data.get('phone_number', ''),
            'dni': self.validated_data.get('dni', ''),
            'birthday': self.validated_data.get('birthday', None),
            'gender': self.validated_data.get('gender', ''),
            'location': self.validated_data.get('location', ''),
            'direction': self.validated_data.get('direction', ''),
            'mutual_code': self.validated_data.get('mutual_code', None),
            'mutual_name': self.validated_data.get('mutual_name', ''),
            'carnet': self.validated_data.get('carnet', ''),
            'lab_client_id': self.validated_data.get('lab_client_id', None),
            'role': 'patient',  # Force role to patient for public registration
        })
        return data

    def save(self, request):
        """Save the user with custom fields."""
        from allauth.account.models import EmailAddress

        user = super().save(request)
        user.first_name = self.validated_data.get('first_name', '')
        user.last_name = self.validated_data.get('last_name', '')
        user.phone_number = self.validated_data.get('phone_number', '')
        user.dni = self.validated_data.get('dni', '')
        user.birthday = self.validated_data.get('birthday', None)
        user.gender = self.validated_data.get('gender', '')
        user.location = self.validated_data.get('location', '')
        user.direction = self.validated_data.get('direction', '')
        user.mutual_code = self.validated_data.get('mutual_code', None)
        user.mutual_name = self.validated_data.get('mutual_name', '')
        user.carnet = self.validated_data.get('carnet', '')
        user.lab_client_id = self.validated_data.get('lab_client_id', None)
        user.role = 'patient'
        user.save()
        return user


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
        extra_kwargs = {
            "first_name": {"required": True, "allow_blank": False},
            "last_name": {"required": True, "allow_blank": False},
            "phone_number": {"required": True, "allow_blank": False},
            "dni": {"required": True, "allow_blank": False},
            "birthday": {"required": True, "allow_null": False},
        }

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

    Role-based validation:
    - Doctors: Only require first_name, last_name, email, matricula
    - Patients: Require full profile (first_name, last_name, phone_number, dni, birthday)
    - Admin/Lab staff: Require basic fields (first_name, last_name)
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
            "matricula",
            "lab_client_id",
        ]

    def validate_role(self, value):
        """Validate that only allowed roles can be created."""
        allowed_roles = ["admin", "doctor", "patient", "lab_staff"]
        if value not in allowed_roles:
            raise serializers.ValidationError(
                f"Invalid role. Allowed roles: {', '.join(allowed_roles)}"
            )
        return value

    def validate(self, attrs):
        """
        Role-based field validation.

        Different roles require different fields:
        - Doctors: first_name, last_name, matricula (minimal data) - email optional
        - Patients: first_name, last_name, email, phone_number, dni, birthday (full profile)
        - Admin/Lab staff: first_name, last_name, email (basic data)
        """
        role = attrs.get("role")

        # All roles require first_name and last_name
        if not attrs.get("first_name"):
            raise serializers.ValidationError(
                {"first_name": "This field is required."}
            )
        if not attrs.get("last_name"):
            raise serializers.ValidationError(
                {"last_name": "This field is required."}
            )

        # Doctor-specific validation (email is optional for doctors)
        if role == "doctor":
            if not attrs.get("matricula"):
                raise serializers.ValidationError(
                    {"matricula": "Matricula is required for doctors."}
                )
            # Email is optional for doctors - no validation needed

        # Patient-specific validation (full profile required including email)
        elif role == "patient":
            if not attrs.get("email"):
                raise serializers.ValidationError(
                    {"email": "Email is required for patients."}
                )
            required_patient_fields = {
                "phone_number": "Phone number is required for patients.",
                "dni": "DNI is required for patients.",
                "birthday": "Birthday is required for patients.",
            }
            for field, error_message in required_patient_fields.items():
                if not attrs.get(field):
                    raise serializers.ValidationError({field: error_message})

        # Admin/Lab staff validation (email required)
        else:
            if not attrs.get("email"):
                raise serializers.ValidationError(
                    {"email": "Email is required for this role."}
                )

        return attrs

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

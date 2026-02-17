"""Management command to create seed users for development."""

from allauth.account.models import EmailAddress
from django.core.management.base import BaseCommand

from apps.users.models import User

SEED_USERS = [
    {
        "email": "admin@labcontrol.com",
        "first_name": "Admin",
        "last_name": "LabControl",
        "role": "admin",
        "is_staff": True,
        "is_superuser": True,
        "lab_client_id": 1,
    },
    {
        "email": "doctor@labcontrol.com",
        "first_name": "Doctor",
        "last_name": "LabControl",
        "role": "doctor",
        "lab_client_id": 1,
    },
    {
        "email": "patient@labcontrol.com",
        "first_name": "Patient",
        "last_name": "LabControl",
        "role": "patient",
        "lab_client_id": 1,
    },
]

PASSWORD = "test1234"


class Command(BaseCommand):
    help = "Create seed users for development (admin, doctor, patient)"

    def handle(self, *args, **options):
        self.stdout.write("Creating seed users...")

        for user_data in SEED_USERS:
            email = user_data["email"]
            extra = {k: v for k, v in user_data.items() if k not in ("email",)}

            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "is_active": True,
                    "is_verified": True,
                    **extra,
                },
            )

            if created:
                user.set_password(PASSWORD)
                user.save(update_fields=["password"])
            else:
                # Ensure existing user is active and verified
                user.is_active = True
                user.is_verified = True
                for key, value in extra.items():
                    setattr(user, key, value)
                user.set_password(PASSWORD)
                user.save()

            # Create/update allauth EmailAddress entry so login works
            EmailAddress.objects.update_or_create(
                user=user,
                email=email,
                defaults={"verified": True, "primary": True},
            )

            status = "created" if created else "already exists (updated)"
            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✓ [{user.role}] {email} — {status}"
                )
            )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Seed users ready!"))
        self.stdout.write(f"  Password: {PASSWORD}")
        self.stdout.write("  Users:")
        for u in SEED_USERS:
            self.stdout.write(f"    {u['role']:10s}  {u['email']}")

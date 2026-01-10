from django.core.management.base import BaseCommand
from allauth.account.models import EmailAddress
from apps.users.models import User


class Command(BaseCommand):
    help = "Verify email address for a user"

    def add_arguments(self, parser):
        parser.add_argument("email", type=str, help="User email address")

    def handle(self, *args, **options):
        email = options["email"]
        try:
            user = User.objects.get(email=email)
            email_address, created = EmailAddress.objects.get_or_create(
                user=user,
                email=email,
                defaults={"verified": True, "primary": True},
            )
            if not created:
                email_address.verified = True
                email_address.primary = True
                email_address.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Email {email} verified successfully (already existed)"
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Email {email} verified successfully (created new)"
                    )
                )
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f"User with email {email} not found")
            )

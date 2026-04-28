from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Create initial superuser from environment variables if it does not exist"

    def handle(self, *args, **options):
        User = get_user_model()

        username = "MRPG2"
        email = "mrpg2@example.com"
        password = "Analytics"

        if not username or not password:
            self.stdout.write(self.style.WARNING("Bootstrap admin skipped: missing username/password"))
            return

        user = User.objects.filter(username=username).first()

        if user:
            updated = False

            if not user.is_staff:
                user.is_staff = True
                updated = True

            if not user.is_superuser:
                user.is_superuser = True
                updated = True

            if email and user.email != email:
                user.email = email
                updated = True

            if updated:
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Updated existing admin user: {username}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"Admin user already exists: {username}"))
            return

        User.objects.create_superuser(
            username=username,
            email=email,
            password=password
        )
        self.stdout.write(self.style.SUCCESS(f"Created admin user: {username}"))
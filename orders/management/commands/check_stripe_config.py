from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Validate Stripe environment variables without displaying secret values."

    def handle(self, *args, **options):
        secret_key = settings.STRIPE_SECRET_KEY
        publishable_key = settings.STRIPE_PUBLISHABLE_KEY
        webhook_secret = settings.STRIPE_WEBHOOK_SECRET

        if not secret_key:
            raise CommandError(
                "STRIPE_SECRET_KEY is missing. Put it in the project-root .env "
                "file and restart Django (or recreate the Docker containers)."
            )

        if not secret_key.startswith(("sk_test_", "sk_live_", "rk_test_", "rk_live_")):
            raise CommandError(
                "STRIPE_SECRET_KEY is present but does not have a recognised Stripe "
                "secret/restricted-key prefix. Check for a copied label or typo."
            )

        secret_mode = "test" if "_test_" in secret_key else "live"
        if publishable_key:
            expected_prefix = f"pk_{secret_mode}_"
            if not publishable_key.startswith(expected_prefix):
                raise CommandError(
                    "STRIPE_PUBLISHABLE_KEY does not match the secret key's "
                    f"{secret_mode} mode."
                )

        self.stdout.write(self.style.SUCCESS(
            f"Stripe Checkout is configured in {secret_mode} mode."
        ))
        if not publishable_key:
            self.stdout.write(
                "STRIPE_PUBLISHABLE_KEY is not set; that is valid for the current "
                "Stripe-hosted Checkout flow."
            )
        if not webhook_secret:
            self.stdout.write(self.style.WARNING(
                "STRIPE_WEBHOOK_SECRET is not set. Checkout redirects can work, "
                "but signed webhook events will not."
            ))

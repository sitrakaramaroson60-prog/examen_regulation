from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Désactive les comptes sans connexion depuis N jours (défaut 180)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=180)

    def handle(self, *args, **options):
        limit = timezone.now() - timedelta(days=options["days"])
        qs = User.objects.filter(is_active=True, is_superuser=False).filter(
            Q(last_login__lt=limit) | Q(last_login__isnull=True, date_joined__lt=limit)
        )
        count = qs.update(is_active=False)
        self.stdout.write(f"{count} compte(s) désactivé(s).")

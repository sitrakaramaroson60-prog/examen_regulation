from django.core.management.base import BaseCommand

from apps.organizations.models import Organization

INITIAL = [
    ("ARTEC", "ARTEC", Organization.Type.REGULATOR),
    ("YAS", "YAS", Organization.Type.OPERATOR),
    ("AIRTEL", "AIRTEL", Organization.Type.OPERATOR),
    ("ORANGE", "ORANGE", Organization.Type.OPERATOR),
]


class Command(BaseCommand):
    help = "Crée (idempotent) les organisations initiales : ARTEC, YAS, AIRTEL, ORANGE."

    def handle(self, *args, **options):
        for name, code, org_type in INITIAL:
            _, created = Organization.objects.update_or_create(
                code=code, defaults={"name": name, "organization_type": org_type, "is_active": True}
            )
            self.stdout.write(f"{'Créée' if created else 'Existante'} : {code}")

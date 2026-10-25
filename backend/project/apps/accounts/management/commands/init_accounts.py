"""Crée les comptes initiaux de la plateforme (idempotent).

Comptes : 3 comptes opérateurs (YAS, AIRTEL, ORANGE), ARTEC Régulation et Prédiction, ARTEC Publications
et un administrateur système. Aucun mot de passe n'est écrit dans le code :
  * INITIAL_ACCOUNTS_PASSWORD (variable d'environnement) ou --password => mot de passe commun ;
  * sinon un mot de passe aléatoire est généré pour chaque compte et AFFICHÉ UNE SEULE FOIS.
Un compte déjà existant n'est jamais modifié (utilisez --reset-passwords pour régénérer les mots de passe).
"""
import os
import secrets
import string

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role, User
from apps.organizations.models import Organization

ACCOUNTS = [
    # (identifiant local, rôle, organisation, prénom, nom)
    ("yas", Role.OPERATOR_USER, "YAS", "Compte", "YAS"),
    ("airtel", Role.OPERATOR_USER, "AIRTEL", "Compte", "AIRTEL"),
    ("orange", Role.OPERATOR_USER, "ORANGE", "Compte", "ORANGE"),
    ("artec.regulation", Role.ARTEC_REGULATOR, "ARTEC", "ARTEC", "Régulation et Prédiction"),
    ("artec.publications", Role.ARTEC_PUBLISHER, "ARTEC", "ARTEC", "Publications"),
    ("admin", Role.SYSTEM_ADMIN, "ARTEC", "Administrateur", "Système"),
]


def random_password(length=16):
    alphabet = string.ascii_letters + string.digits + "!@#$%*-_"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.islower() for c in pwd) and any(c.isupper() for c in pwd) and sum(c.isdigit() for c in pwd) >= 2 and any(c in "!@#$%*-_" for c in pwd):
            return pwd


class Command(BaseCommand):
    help = "Crée les comptes initiaux (3 opérateurs, ARTEC régulation, ARTEC publications, administrateur)."

    def add_arguments(self, parser):
        parser.add_argument("--domain", default=os.environ.get("INITIAL_ACCOUNTS_DOMAIN", "plateforme.local"), help="Domaine des adresses email créées.")
        parser.add_argument("--password", default=os.environ.get("INITIAL_ACCOUNTS_PASSWORD"), help="Mot de passe commun (sinon aléatoires).")
        parser.add_argument("--reset-passwords", action="store_true", help="Régénère le mot de passe des comptes existants.")

    def handle(self, *args, **opts):
        common = opts["password"]
        if common:
            try:
                validate_password(common)
            except ValidationError as exc:
                raise CommandError("Mot de passe refusé : " + " ".join(exc.messages))
        rows = []
        for local, role, org_code, first, last in ACCOUNTS:
            org = Organization.objects.filter(code=org_code).first()
            if org is None:
                raise CommandError("Organisations absentes : exécutez d'abord `python manage.py init_organizations`.")
            email = f"{local}@{opts['domain']}"
            user = User.objects.filter(email=email).first()
            if user and not opts["reset_passwords"]:
                rows.append((email, role, "(compte existant, inchangé)"))
                continue
            pwd = common or random_password()
            if user is None:
                User.objects.create_user(email=email, password=pwd, role=role, organization=org, first_name=first, last_name=last)
            else:
                user.set_password(pwd)
                user.failed_login_attempts, user.locked_until = 0, None
                user.save()
            rows.append((email, role, pwd if not common else "(mot de passe commun fourni)"))
        self.stdout.write(self.style.SUCCESS("Comptes initiaux :"))
        for email, role, pwd in rows:
            self.stdout.write(f"  {email:<38} {role:<17} {pwd}")
        if not common and any(not r[2].startswith("(") for r in rows):
            self.stdout.write(self.style.WARNING("Notez ces mots de passe maintenant : ils ne seront plus affichés."))

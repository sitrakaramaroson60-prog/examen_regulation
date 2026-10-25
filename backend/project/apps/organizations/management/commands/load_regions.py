"""Charge un référentiel région/ville depuis un fichier JSON fourni par l'ARTEC.

Format : {"Région": ["Ville 1", "Ville 2"], ...}

Aucune liste n'est présentée comme officielle : le fichier `data/regions_sample.json`
n'est qu'un EXEMPLE minimal (issu de la maquette) à remplacer par le référentiel validé.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from apps.organizations.models import City, Region

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "data" / "regions_sample.json"


class Command(BaseCommand):
    help = "Charge régions et villes depuis un fichier JSON (exemple fourni, non officiel)."

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DEFAULT_FILE))

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.exists():
            raise CommandError(f"Fichier introuvable : {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        for region_name, cities in data.items():
            region, _ = Region.objects.get_or_create(name=region_name, defaults={"code": slugify(region_name)})
            for city_name in cities:
                City.objects.get_or_create(region=region, name=city_name)
        self.stdout.write(self.style.SUCCESS(f"{Region.objects.count()} régions, {City.objects.count()} villes."))
        if path == DEFAULT_FILE:
            self.stdout.write(self.style.WARNING("Jeu d'exemple NON OFFICIEL : remplacez-le par le référentiel validé."))

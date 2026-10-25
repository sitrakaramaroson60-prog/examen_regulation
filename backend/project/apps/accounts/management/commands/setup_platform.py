from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Initialisation complète : organisations, régions/villes d'exemple (optionnel) et comptes initiaux."

    def add_arguments(self, parser):
        parser.add_argument("--skip-regions", action="store_true")
        parser.add_argument("--regions-file", default=None, help="Référentiel région/ville JSON validé.")

    def handle(self, *args, **opts):
        call_command("init_organizations")
        if not opts["skip_regions"]:
            call_command("load_regions", *(["--file", opts["regions_file"]] if opts["regions_file"] else []))
        call_command("init_accounts")

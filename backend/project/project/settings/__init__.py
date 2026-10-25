# Compatibilité : si DJANGO_SETTINGS_MODULE vaut simplement « project.settings »
# (ancien manage.py de startproject), on charge la configuration de développement.
# Pour la production, utilisez explicitement project.settings.prod.
from .dev import *  # noqa: F401,F403

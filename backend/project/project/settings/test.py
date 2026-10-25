import tempfile
from pathlib import Path

from .base import *  # noqa

DEBUG = False
SECRET_KEY = "test-only-key-not-used-anywhere-else-0123456789"
# Par défaut : SQLite en mémoire (rapide). Pour tester sur PostgreSQL : définir TEST_ON_POSTGRES=true
# (les paramètres DB_* du .env sont alors utilisés ; Django crée une base « test_<DB_NAME> »).
if not env_bool("TEST_ON_POSTGRES", False):  # noqa: F405
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
PRIVATE_MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="telecom_test_media_"))
ML_MODELS_DIR = PRIVATE_MEDIA_ROOT / "models"
SURVEY_TOKEN_MIN_SECONDS = 0
SURVEY_PUBLIC_MIN_RESPONDENTS = 2
ML_MIN_TRAINING_ROWS = 60
ML_MIN_ROWS_PER_CLASS = 10
ML_MIN_GROUPS = 4
SCRAPING_ALLOWED_DOMAINS = ["example.org"]
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100000/hour",
        "user": "100000/hour",
        "login": "100000/min",
        "public_survey": "100000/hour",
        "public_comment": "100000/hour",
        "public_complaint": "100000/hour",
        "realtime": "100000/hour",
    },
}

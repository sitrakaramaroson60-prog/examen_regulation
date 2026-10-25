"""Paramètres communs. Toute valeur sensible est lue depuis l'environnement."""
import os
from datetime import timedelta
from pathlib import Path

from django.core.management.utils import get_random_secret_key

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:  # pragma: no cover
    pass

BASE_DIR = Path(__file__).resolve().parents[2]


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return str(env(name, str(default))).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)
# Aucune clé par défaut n'est inscrite dans le code : en l'absence de variable,
# une clé éphémère est générée (sessions/jetons invalidés à chaque redémarrage).
SECRET_KEY = env("DJANGO_SECRET_KEY") or get_random_secret_key()
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "daphne",  # doit précéder staticfiles : `runserver` sert alors aussi les WebSockets (ASGI)
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
    "channels",
    "apps.common",
    "apps.realtime",
    "apps.accounts",
    "apps.organizations",
    "apps.audit",
    "apps.notifications",
    "apps.publications",
    "apps.surveys",
    "apps.datasets",
    "apps.qos",
    "apps.predictions",
    "apps.regulation",
    "apps.complaints",
    "apps.scraping",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "project.urls"
WSGI_APPLICATION = "project.wsgi.application"
ASGI_APPLICATION = "project.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

# PostgreSQL est la base de données du projet (paramètres lus dans .env).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "telecom_regulation"),
        "USER": env("DB_USER", "postgres"),
        "PASSWORD": env("DB_PASSWORD", ""),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Indian/Antananarivo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Stockage privé : aucun fichier importé n'est servi via une URL publique.
PRIVATE_MEDIA_ROOT = Path(env("PRIVATE_MEDIA_ROOT", str(BASE_DIR / "private_media"))).resolve()
MAX_UPLOAD_SIZE_MB = int(env("MAX_UPLOAD_SIZE_MB", "20"))
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

REDIS_URL = env("REDIS_URL", "")
# Temps réel : Redis est nécessaire pour diffuser entre processus (workers Celery, plusieurs serveurs).
# Sans Redis, une couche en mémoire sert un seul processus ; le polling de secours rattrape le reste.
if REDIS_URL:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels_redis.core.RedisChannelLayer", "CONFIG": {"hosts": [REDIS_URL]}}}
else:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
if REDIS_URL:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "300/hour",
        "user": "3000/hour",
        "login": "10/min",
        "public_survey": "30/hour",
        "public_comment": "10/hour",
        "public_complaint": "5/hour",
        "realtime": "20000/hour",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(env("JWT_ACCESS_MINUTES", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(hours=int(env("JWT_REFRESH_HOURS", "12"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "CHECK_REVOKE_TOKEN": True,  # un changement de mot de passe révoque les jetons existants
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Plateforme de régulation des télécommunications — API",
    "DESCRIPTION": "API REST du backend (ARTEC, YAS, AIRTEL, ORANGE).",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
CORS_ALLOW_CREDENTIALS = False
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "")

# --- Celery ---
CELERY_BROKER_URL = env("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_TIME_LIMIT = 15 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 12 * 60
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "publish-scheduled-publications": {"task": "publications.publish_due", "schedule": 60.0},
    "purge-realtime-events": {"task": "realtime.purge_events", "schedule": 3600.0},
    "dispatch-scraping-jobs": {"task": "scraping.dispatch_due_jobs", "schedule": 300.0},
    "evaluate-obligations": {"task": "regulation.evaluate_obligations", "schedule": 6 * 3600.0},
    "notify-approaching-deadlines": {"task": "regulation.notify_deadlines", "schedule": 3600.0},
}

# --- Règles métier configurables ---
LOGIN_MAX_FAILED_ATTEMPTS = 5
LOGIN_LOCK_MINUTES = 15
SURVEY_OPERATOR_APPROVAL_REQUIRED = env_bool("SURVEY_OPERATOR_APPROVAL_REQUIRED", True)
SURVEY_PUBLIC_MIN_RESPONDENTS = int(env("SURVEY_PUBLIC_MIN_RESPONDENTS", "5"))
SURVEY_FINGERPRINT_SALT = env("SURVEY_FINGERPRINT_SALT") or SECRET_KEY
SURVEY_TOKEN_MIN_SECONDS = 3
SURVEY_TOKEN_MAX_SECONDS = 2 * 3600
SCRAPING_ALLOWED_DOMAINS = env_list("SCRAPING_ALLOWED_DOMAINS", "")
SCRAPING_USER_AGENT = env("SCRAPING_USER_AGENT", "ARTEC-QoS-Collector/1.0")
SCRAPING_TIMEOUT_SECONDS = 10
SCRAPING_MAX_BYTES = 2 * 1024 * 1024
SCRAPING_MAX_REDIRECTS = 3
ML_MIN_TRAINING_ROWS = int(env("ML_MIN_TRAINING_ROWS", "300"))
ML_MIN_ROWS_PER_CLASS = int(env("ML_MIN_ROWS_PER_CLASS", "30"))
ML_MIN_GROUPS = int(env("ML_MIN_GROUPS", "5"))
ML_MODELS_DIR = PRIVATE_MEDIA_ROOT / "models"
ML_MIN_MACRO_F1 = float(env("ML_MIN_MACRO_F1", "0.5"))
ML_REVIEW_CONFIDENCE = float(env("ML_REVIEW_CONFIDENCE", "0.6"))  # sous ce score, le résultat est signalé « à vérifier »
# Publication publique d'un baromètre QoS : désactivée par défaut (décision de l'ARTEC).
QOS_PUBLIC_ENABLED = env_bool("QOS_PUBLIC_ENABLED", False)
QOS_PUBLIC_MIN_MEASUREMENTS = int(env("QOS_PUBLIC_MIN_MEASUREMENTS", "30"))

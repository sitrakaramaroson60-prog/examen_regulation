from .base import *  # noqa

DEBUG = env_bool("DJANGO_DEBUG", True)
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:8443")
# Sans Redis configuré, les tâches Celery s'exécutent de façon synchrone (confort de développement).
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_EAGER", not env("REDIS_URL"))

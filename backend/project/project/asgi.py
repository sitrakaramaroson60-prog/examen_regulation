import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings.prod")
django_asgi_app = get_asgi_application()  # initialise Django avant d'importer les consommateurs

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import OriginValidator  # noqa: E402
from django.conf import settings  # noqa: E402
from django.urls import path  # noqa: E402

from apps.realtime.consumers import RealtimeConsumer  # noqa: E402

# Seules les origines autorisées (CORS_ALLOWED_ORIGINS) et les hôtes de l'API peuvent ouvrir un WebSocket.
origins = list(settings.CORS_ALLOWED_ORIGINS) + [h for h in settings.ALLOWED_HOSTS if h]

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": OriginValidator(URLRouter([path("ws/realtime/", RealtimeConsumer.as_asgi())]), origins),
})

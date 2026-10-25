from django.db.models import Max, Min
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .bus import audiences_for
from .models import RealtimeEvent

MAX_EVENTS = 200


class EventsView(APIView):
    """Rattrapage / repli du temps réel : événements postérieurs à `after` destinés à l'appelant.

    * sans `after` : renvoie seulement le curseur courant ;
    * `reset: true` si le client a trop de retard (événements purgés ou trop nombreux) : il doit tout recharger.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "realtime"

    @extend_schema(responses={200: dict})
    def get(self, request):
        last = RealtimeEvent.objects.aggregate(m=Max("id"))["m"] or 0
        raw = request.query_params.get("after")
        if raw is None or not raw.lstrip("-").isdigit():
            return Response({"last_id": last, "events": [], "reset": False})
        after = int(raw)
        if after > last:  # curseur d'une base réinitialisée
            return Response({"last_id": last, "events": [], "reset": True})
        first = RealtimeEvent.objects.aggregate(m=Min("id"))["m"]
        if first is not None and after + 1 < first and after != 0 and RealtimeEvent.objects.filter(id__gt=after).count() == RealtimeEvent.objects.count():
            reset_hint = True
        else:
            reset_hint = False
        qs = RealtimeEvent.objects.filter(id__gt=after, audience__in=audiences_for(request.user)).order_by("id")
        rows = list(qs.values("id", "topic", "action", "ref_type", "ref_id")[: MAX_EVENTS + 1])
        if len(rows) > MAX_EVENTS or reset_hint:
            return Response({"last_id": last, "events": [], "reset": True})
        return Response({"last_id": last, "events": rows, "reset": False})

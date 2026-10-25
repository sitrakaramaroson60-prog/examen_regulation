import time

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from .bus import PUBLIC, audiences_for, group_name


class RealtimeConsumer(AsyncJsonWebsocketConsumer):
    """Canal WebSocket : le client s'identifie par un premier message {"type": "auth", "token": "<jeton d'accès>"} (le jeton
    n'apparaît donc jamais dans l'URL ni dans les journaux). Sans authentification, seul le public « public » est servi."""

    async def connect(self):
        self.audiences = set()
        self.exp = None
        await self._join([PUBLIC])
        await self.accept()
        await self.send_json({"type": "ready", "authenticated": False})

    async def disconnect(self, code):
        for a in list(self.audiences):
            await self.channel_layer.group_discard(group_name(a), self.channel_name)

    async def receive_json(self, content, **kwargs):
        kind = content.get("type") if isinstance(content, dict) else None
        if kind == "ping":
            await self.send_json({"type": "pong"})
        elif kind == "auth":
            await self._authenticate(content.get("token"))

    async def _authenticate(self, token):
        user, exp = None, None
        if token:
            try:
                access = AccessToken(token)
                user = await self._load_user(access["user_id"])
                exp = int(access["exp"])
            except (TokenError, KeyError):
                user = None
        if user is None and token:
            await self._set([PUBLIC])
            self.exp = None
            await self.send_json({"type": "auth_error"})
            return
        await self._set(audiences_for(user))
        self.exp = exp
        await self.send_json({"type": "ready", "authenticated": user is not None})

    @database_sync_to_async
    def _load_user(self, user_id):
        from apps.accounts.models import User

        return User.objects.filter(pk=user_id, is_active=True).select_related("organization").first()

    async def _join(self, audiences):
        for a in audiences:
            if a not in self.audiences:
                await self.channel_layer.group_add(group_name(a), self.channel_name)
                self.audiences.add(a)

    async def _set(self, audiences):
        for a in list(self.audiences - set(audiences)):
            await self.channel_layer.group_discard(group_name(a), self.channel_name)
            self.audiences.discard(a)
        await self._join(audiences)

    async def realtime_event(self, message):
        # le jeton d'accès a une durée de vie courte : à l'expiration, retour au public anonyme
        if self.exp is not None and time.time() > self.exp:
            await self._set([PUBLIC])
            self.exp = None
            await self.send_json({"type": "auth_expired"})
        ev = message["event"]
        if ev["audience"] in self.audiences:
            await self.send_json({"type": "event", **{k: ev[k] for k in ("id", "topic", "action", "ref_type", "ref_id")}})

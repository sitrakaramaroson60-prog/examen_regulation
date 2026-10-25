from django.db import models


class RealtimeEvent(models.Model):
    """Journal des événements temps réel. Il ne contient AUCUNE donnée métier : seulement « quoi » a changé et pour quel
    public. Le client recharge ensuite les données par l'API, qui applique les permissions habituelles."""

    topic = models.CharField(max_length=40)
    audience = models.CharField(max_length=60)  # public | org:<id> | role:<ROLE> | user:<id>
    action = models.CharField(max_length=20, default="changed")
    ref_type = models.CharField(max_length=40, blank=True)
    ref_id = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["audience", "id"])]
        ordering = ["id"]

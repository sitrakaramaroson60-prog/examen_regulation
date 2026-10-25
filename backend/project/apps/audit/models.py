from django.db import models


class AuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError("Les journaux d'audit sont immuables.")

    def delete(self):
        raise PermissionError("Les journaux d'audit sont immuables.")


class AuditLog(models.Model):
    actor = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    actor_email = models.CharField(max_length=254, blank=True)
    actor_organization = models.ForeignKey("organizations.Organization", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=80, db_index=True)
    resource_type = models.CharField(max_length=80, blank=True)
    resource_id = models.CharField(max_length=64, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    objects = AuditQuerySet.as_manager()

    class Meta:
        ordering = ["-timestamp", "-id"]
        indexes = [models.Index(fields=["resource_type", "resource_id"])]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("Les journaux d'audit sont immuables.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Les journaux d'audit sont immuables.")

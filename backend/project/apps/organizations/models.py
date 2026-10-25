from django.db import models

from apps.common.models import TimeStampedModel


class Organization(TimeStampedModel):
    class Type(models.TextChoices):
        REGULATOR = "REGULATOR", "Régulateur"
        OPERATOR = "OPERATOR", "Opérateur"

    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=20, unique=True)
    organization_type = models.CharField(max_length=20, choices=Type.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code

    @property
    def is_regulator(self):
        return self.organization_type == self.Type.REGULATOR


class Region(models.Model):
    name = models.CharField(max_length=120, unique=True)
    code = models.SlugField(max_length=40, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class City(models.Model):
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="cities")
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["region__name", "name"]
        verbose_name_plural = "cities"
        constraints = [models.UniqueConstraint(fields=["region", "name"], name="uniq_city_per_region")]

    def __str__(self):
        return f"{self.name} ({self.region.name})"
